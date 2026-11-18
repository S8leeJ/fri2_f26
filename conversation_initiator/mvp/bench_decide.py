#!/usr/bin/env python3
"""Time the decision call of Jev and of Groq on the same scenes.

    python3 bench_decide.py                    # 20 calls each, Jev and Groq in turn
    python3 bench_decide.py --live             # scenes from the robot's sensors now
    python3 bench_decide.py --n 10 --providers jev
    python3 bench_decide.py --scenes logs      # scenes from the newest live_logs file

Each call is the call live_node.py makes with no rules: Jev gets the typed
questions, and Groq gets SYSTEM_6_SCENE and Decision6. mvp.ask times only the
network call. Waits for a busy server are not in the time.

--live reads /social_context from fusion_publisher.py and builds each scene as
live_node.py does. It uses only scenes with a person in view, at most one each
--every seconds. It does not speak, move, or publish. Do not run live_node.py at
the same time, because its calls use the same network.

One call to each provider before the timed calls opens the connection, as
live_node.py does at start. The calls alternate between the providers, and the
first provider changes at each scene, so both providers see the same network.

The timeout is 10 s, so a slow call gets a time. live_node.py drops a call
after 2 s (--timeout). The ">2 s" column counts the calls that it would drop.
Ctrl+C stops early and prints the results so far.
"""

from __future__ import annotations

import argparse
import datetime
import itertools
import json
import os
import pathlib
import statistics
import sys
import threading
import time
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Tuple

import dotenv

import mvp
from context import validate
from fusion_adapter import Memory, fusion_to_context

HERE = pathlib.Path(__file__).resolve().parent
LIVE_LOGS = HERE / "live_logs"
RESULTS = HERE / "bench_results"
LIVE_LIMIT_MS = 2000.0
# A live scene older than this is not used: fusion stopped or is behind.
LIVE_STALE_S = 2.0
PERSON_FIELDS = ("distance_m", "facing_robot", "gaze_at_robot_s", "motion")

Scene = Tuple[str, dict]


def load_scenes(source: str, live_logs: pathlib.Path = LIVE_LOGS) -> List[Scene]:
    if source == "vignettes":
        return [(v["file"], v["context"]) for v in mvp.load_vignettes()]
    files = sorted(live_logs.glob("*.jsonl"))
    if not files:
        sys.exit("no live_logs/*.jsonl files. Use --scenes vignettes.")
    scenes = []
    for i, line in enumerate(files[-1].read_text().splitlines(), 1):
        try:
            ctx = json.loads(line).get("context")
        except ValueError:
            continue
        if ctx and ctx.get("target"):
            scenes.append(("%s:%d" % (files[-1].name, i), ctx))
    if not scenes:
        sys.exit("no scene with a person in %s. Use --scenes vignettes." % files[-1])
    return scenes


class LiveScenes:
    """The newest scene from /social_context, built as live_node.py builds it."""

    def __init__(self):
        self.mem = Memory()
        self.ctx: Optional[dict] = None
        self.count = 0
        self.lock = threading.Lock()

    def on_message(self, data: str, now: float) -> None:
        try:
            msg = json.loads(data)
        except ValueError:
            return
        with self.lock:
            ctx = fusion_to_context(msg, self.mem, now)
        try:
            validate(ctx)
        except ValueError:
            return
        with self.lock:
            self.ctx = ctx

    def take(self, now: float) -> Optional[Scene]:
        with self.lock:
            ctx = self.ctx
        if ctx is None or now - ctx["t"] > LIVE_STALE_S or not ctx.get("target"):
            return None
        self.count += 1
        return "live:%d" % self.count, ctx


def live_scenes(source: LiveScenes, every: float, clock: Callable = time.time,
                sleep: Callable = time.sleep, say: Callable = print) -> Iterator[Scene]:
    """The newest scene with a person, at most once each `every` seconds."""
    next_t = last_said = 0.0
    while True:
        now = clock()
        if now < next_t:
            sleep(min(0.05, next_t - now))
            continue
        scene = source.take(now)
        if scene is None:
            if now - last_said >= 5.0:
                say("waiting for a person in front of the robot (is fusion_publisher.py running?)")
                last_said = now
            sleep(0.1)
            continue
        next_t = now + every
        yield scene


def ros_source() -> LiveScenes:
    """Subscribe to /social_context in a background thread."""
    # Must match fusion_publisher.py, or this node cannot see it.
    os.environ["ROS_LOCALHOST_ONLY"] = "1"
    try:
        import rclpy
        from std_msgs.msg import String
    except ImportError as error:
        if os.environ.get("BENCH_ROS_LOADED"):
            sys.exit("ROS 2 does not load, even after /opt/ros/humble/setup.bash: %s" % error)
        os.environ["BENCH_ROS_LOADED"] = "1"
        os.execvp("bash", ["bash", "-c", 'source /opt/ros/humble/setup.bash && exec "$0" "$@"',
                           sys.executable, os.path.abspath(__file__), *sys.argv[1:]])
    rclpy.init()
    node = rclpy.create_node("bench_decide")
    source = LiveScenes()
    node.create_subscription(String, "/social_context",
                             lambda m: source.on_message(m.data, time.time()), 10)

    def spin():
        try:
            while rclpy.ok():
                rclpy.spin_once(node, timeout_sec=0.1)
        except Exception:  # noqa: BLE001 - the context closes when the script ends
            pass

    threading.Thread(target=spin, daemon=True).start()
    return source


def model_for(provider: str, groq_model: Optional[str] = None) -> str:
    if provider == "groq":
        return groq_model or os.environ.get("GROQ_MODEL") or mvp.DEFAULT_MODEL["groq"]
    return mvp.DEFAULT_MODEL[provider]


def call(provider: str, client, model: str, ctx: dict, ask: Callable = mvp.ask) -> dict:
    try:
        d, ms, thoughts = ask(provider, client, model, mvp.SYSTEM_6_SCENE, json.dumps(ctx),
                              mvp.Decision6, 400)
    except Exception as e:  # noqa: BLE001 - a failed call is counted, not fatal
        kind = "timeout" if mvp.is_timeout(e) else type(e).__name__
        return {"ms": None, "error": "%s: %s" % (kind, str(e)[:200])}
    return {"ms": round(ms, 1), "action": d.action, "reasoning_tokens": thoughts}


def run(providers: List[str], clients: Dict[str, object], models: Dict[str, str],
        scenes: Iterable[Scene], n: int, ask: Callable = mvp.ask, show: bool = True) -> List[dict]:
    """A list of scenes is used again from the start when it runs out."""
    it = itertools.cycle(scenes) if isinstance(scenes, list) else iter(scenes)
    rows: List[dict] = []
    try:
        first = next(it)
        for p in providers:
            warm = call(p, clients[p], models[p], first[1], ask)
            if show:
                print("warm-up %-5s %s" % (p, warm.get("error") or "%.0f ms (not counted)" % warm["ms"]))
        it = itertools.chain([first], it)
        for i in range(n):
            name, ctx = next(it)
            person = {k: ctx["target"][k] for k in PERSON_FIELDS if k in (ctx.get("target") or {})}
            order = providers if i % 2 == 0 else providers[::-1]
            for p in order:
                row = {"call": i + 1, "provider": p, "scene": name, "person": person,
                       **call(p, clients[p], models[p], ctx, ask)}
                rows.append(row)
                if show:
                    print("%3d  %-5s %-28s %s" % (i + 1, p, name[:28], row.get("error") or "%7.0f ms  %s" % (
                        row["ms"], row["action"])))
    except KeyboardInterrupt:
        print("\nstopped early")
    return rows


def summarize(rows: List[dict], provider: str) -> dict:
    mine = [r for r in rows if r["provider"] == provider]
    ms = [r["ms"] for r in mine if r["ms"] is not None]
    tokens = [r["reasoning_tokens"] for r in mine if r.get("reasoning_tokens") is not None]
    out = {"provider": provider, "n": len(ms), "failed": len(mine) - len(ms),
           "over_2s": sum(m > LIVE_LIMIT_MS for m in ms),
           "median_ms": None, "sd_ms": None, "mean_ms": None, "min_ms": None, "max_ms": None,
           "median_reasoning_tokens": statistics.median(tokens) if tokens else None}
    if ms:
        out.update(median_ms=statistics.median(ms), mean_ms=statistics.mean(ms),
                   min_ms=min(ms), max_ms=max(ms),
                   sd_ms=statistics.stdev(ms) if len(ms) > 1 else None)
    return out


def _f(x: Optional[float]) -> str:
    return "-" if x is None else "%.0f" % x


SCENE_WORDS = {"vignettes": "test scenes", "logs": "logged scenes",
               "live": "live scenes from the robot's camera and microphone"}


def report(summaries: List[dict], models: Dict[str, str], n_scenes: int, source: str) -> str:
    lines = ["provider  model                       n  median     SD   mean    min    max  >2 s  failed"]
    for s in summaries:
        lines.append("%-8s  %-24s %3d  %6s %6s %6s %6s %6s  %4d  %6d" % (
            s["provider"], models[s["provider"]][:24], s["n"], _f(s["median_ms"]), _f(s["sd_ms"]),
            _f(s["mean_ms"]), _f(s["min_ms"]), _f(s["max_ms"]), s["over_2s"], s["failed"]))
    lines.append("(ms per decision call, warm connection, %d scenes from %s)" % (n_scenes, source))
    for s in summaries:
        if s["median_reasoning_tokens"] is not None:
            lines.append("%s reasoning tokens before the answer, median per call: %.0f" % (
                s["provider"], s["median_reasoning_tokens"]))
    parts = []
    for s in summaries:
        if s["median_ms"] is None:
            continue
        name = "Jev" if s["provider"] == "jev" else "Groq (%s)" % models[s["provider"]]
        parts.append("%s took a median of %s ms (SD %s ms, n = %d)" % (
            name, _f(s["median_ms"]), _f(s["sd_ms"]), s["n"]))
    if parts:
        lines.append("")
        lines.append("Paper: On the robot, with the same %d %s, %s per decision." % (
            n_scenes, SCENE_WORDS.get(source, "scenes"), "; ".join(parts)))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--providers", default="jev,groq", help="comma list (default jev,groq)")
    ap.add_argument("--n", type=int, default=20, help="timed calls per provider (default 20)")
    ap.add_argument("--live", action="store_true",
                    help="scenes from /social_context now (needs fusion_publisher.py and a person)")
    ap.add_argument("--every", type=float, default=1.0,
                    help="with --live: seconds between scenes, at least (default 1)")
    ap.add_argument("--scenes", choices=("vignettes", "logs"), default="vignettes",
                    help="without --live: vignettes (default) or the newest live_logs file")
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds (default 10)")
    ap.add_argument("--pace", type=float, default=1.0,
                    help="seconds between calls, to stay under rate limits (default 1)")
    ap.add_argument("--groq-model", help="default: GROQ_MODEL in .env, else %s" % mvp.DEFAULT_MODEL["groq"])
    args = ap.parse_args()

    dotenv.load_dotenv(HERE / ".env")
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    for p in providers:
        if p not in mvp.DEFAULT_MODEL:
            sys.exit("unknown provider: %s" % p)
        if not os.environ.get(mvp.ENV_KEY[p]):
            sys.exit("%s is not set in .env" % mvp.ENV_KEY[p])

    source_name = "live" if args.live else args.scenes
    # ros_source() may start this script again with ROS loaded, so it comes first.
    scenes = live_scenes(ros_source(), args.every) if args.live else load_scenes(args.scenes)
    mvp.use_rules(False)
    mvp.PACING.update(pace_s=args.pace, busy_retries=4)
    models = {p: model_for(p, args.groq_model) for p in providers}
    clients = {p: mvp.make_client(p, args.timeout) for p in providers}
    print("%d calls each for %s, scenes from %s, timeout %.0f s" % (
        args.n, ", ".join("%s (%s)" % (p, models[p]) for p in providers), source_name, args.timeout))
    if args.live:
        print("Stand 1 to 2 m in front of the camera. Look at the robot, look away, move a little.")

    started = time.time()
    rows = run(providers, clients, models, scenes, args.n)
    summaries = [summarize(rows, p) for p in providers]
    text = report(summaries, models, len({r["scene"] for r in rows}), source_name)

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = RESULTS / ("decision_time_%s_%s.json" % (source_name, stamp))
    path.write_text(json.dumps({
        "started": datetime.datetime.fromtimestamp(started).isoformat(timespec="seconds"),
        "seconds": round(time.time() - started, 1), "args": vars(args), "models": models,
        "busy_retries_used": mvp.busy_retries_used, "summary": summaries, "calls": rows}, indent=1))

    print("\n----- paste from here -----")
    print(text)
    if mvp.busy_retries_used:
        print("Busy-server retries: %d (waits not in the times)." % mvp.busy_retries_used)
    print("Saved %s" % path)


if __name__ == "__main__":
    main()
