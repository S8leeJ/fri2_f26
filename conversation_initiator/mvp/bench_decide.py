#!/usr/bin/env python3
"""Time the decision call of Jev and of Groq on the same scenes.

    python3 bench_decide.py                    # 20 calls each, Jev and Groq in turn
    python3 bench_decide.py --n 10 --providers jev
    python3 bench_decide.py --scenes live      # scenes from the newest live_logs file

Each call is the call live_node.py makes with no rules: Jev gets the typed
questions, and Groq gets SYSTEM_6_SCENE and Decision6. mvp.ask times only the
network call. Waits for a busy server are not in the time.

One call to each provider before the timed calls opens the connection, as
live_node.py does at start. The calls alternate between the providers, and the
first provider changes at each scene, so both providers see the same network.

The timeout is 10 s, so a slow call gets a time. live_node.py drops a call
after 2 s (--timeout). The ">2 s" column counts the calls that it would drop.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import statistics
import sys
import time
from typing import Callable, Dict, List, Optional, Tuple

import dotenv

import mvp

HERE = pathlib.Path(__file__).parent
LIVE_LOGS = HERE / "live_logs"
RESULTS = HERE / "bench_results"
LIVE_LIMIT_MS = 2000.0

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
        scenes: List[Scene], n: int, ask: Callable = mvp.ask, show: bool = True) -> List[dict]:
    for p in providers:
        warm = call(p, clients[p], models[p], scenes[0][1], ask)
        if show:
            print("warm-up %-5s %s" % (p, warm.get("error") or "%.0f ms (not counted)" % warm["ms"]))
    rows = []
    for i in range(n):
        name, ctx = scenes[i % len(scenes)]
        order = providers if i % 2 == 0 else providers[::-1]
        for p in order:
            row = {"call": i + 1, "provider": p, "scene": name, **call(p, clients[p], models[p], ctx, ask)}
            rows.append(row)
            if show:
                print("%3d  %-5s %-40s %s" % (i + 1, p, name[:40],
                                              row.get("error") or "%7.0f ms  %s" % (row["ms"], row["action"])))
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


def report(summaries: List[dict], models: Dict[str, str], n_scenes: int, source: str) -> str:
    lines = ["provider  model                       n  median     SD   mean    min    max  >2 s  failed"]
    for s in summaries:
        lines.append("%-8s  %-24s %3d  %6s %6s %6s %6s %6s  %4d  %6d" % (
            s["provider"], models[s["provider"]][:24], s["n"], _f(s["median_ms"]), _f(s["sd_ms"]),
            _f(s["mean_ms"]), _f(s["min_ms"]), _f(s["max_ms"]), s["over_2s"], s["failed"]))
    lines.append("(ms per decision call, warm connection, %d scenes from %s)" % (n_scenes, source))
    parts = []
    for s in summaries:
        if s["median_ms"] is None:
            continue
        name = "Jev" if s["provider"] == "jev" else "Groq (%s)" % models[s["provider"]]
        parts.append("%s took a median of %s ms (SD %s ms, n = %d)" % (
            name, _f(s["median_ms"]), _f(s["sd_ms"]), s["n"]))
    if parts:
        lines.append("")
        lines.append("Paper: On the robot, with the same scenes, " + "; ".join(parts) + " per decision.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--providers", default="jev,groq", help="comma list (default jev,groq)")
    ap.add_argument("--n", type=int, default=20, help="timed calls per provider (default 20)")
    ap.add_argument("--scenes", choices=("vignettes", "live"), default="vignettes")
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

    mvp.use_rules(False)
    mvp.PACING.update(pace_s=args.pace, busy_retries=4)
    scenes = load_scenes(args.scenes)
    models = {p: model_for(p, args.groq_model) for p in providers}
    clients = {p: mvp.make_client(p, args.timeout) for p in providers}
    print("%d calls each for %s, %d scenes from %s, timeout %.0f s" % (
        args.n, ", ".join("%s (%s)" % (p, models[p]) for p in providers), len(scenes),
        args.scenes, args.timeout))

    started = time.time()
    rows = run(providers, clients, models, scenes, args.n)
    summaries = [summarize(rows, p) for p in providers]
    text = report(summaries, models, len({r["scene"] for r in rows}), args.scenes)

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = RESULTS / ("decision_time_%s.json" % stamp)
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
