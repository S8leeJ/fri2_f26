#!/usr/bin/env python3
"""Live initiator: read /social_context from the fusion node, decide, publish.

Run on flexo, after fusion/fusion_publisher.py is up:

    cd ~/fri2_f26/conversation_initiator/mvp
    .venv/bin/python live_node.py                  # dry run: decide and publish only
    .venv/bin/python live_node.py --engaged        # dry run, audio node transcribes
    .venv/bin/python live_node.py --speak          # full loop: the robot talks

Watch the decisions in another terminal:

    ros2 topic echo /initiation_decision --field data

Topics:
    in   /social_context        std_msgs/String  fusion wrapper, 10 Hz
    out  /initiation_decision   std_msgs/String  one JSON per LLM call
    out  /engaged               std_msgs/Bool    1 Hz, only with --speak or --engaged
    out  /robot_speaking        std_msgs/Bool    only with --speak

Each tick: fusion_adapter builds a v2.0 context, the gate decides whether to
ask, and one worker thread at a time calls the LLM and the post-filter. Every
LLM call is appended to live_logs/<date>.jsonl.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys
import threading
import time

# Must match fusion_publisher.py and the audio node, or the nodes cannot see each other.
os.environ["ROS_LOCALHOST_ONLY"] = "1"
try:
    import rclpy
    from rclpy import executors
    from rclpy.node import Node
    from std_msgs.msg import Bool, String
except ImportError as error:
    if os.environ.get("LIVE_ROS_LOADED"):
        sys.exit(f"ROS 2 does not load, even after /opt/ros/humble/setup.bash: {error}")
    os.environ["LIVE_ROS_LOADED"] = "1"
    os.execvp("bash", ["bash", "-c", 'source /opt/ros/humble/setup.bash && exec "$0" "$@"',
                       sys.executable, os.path.abspath(__file__), *sys.argv[1:]])

import dotenv

HERE = pathlib.Path(__file__).resolve().parent
dotenv.load_dotenv(HERE / ".env")

from context import validate  # noqa: E402
from fusion_adapter import Memory, apply_result, consume_pending, fusion_to_context  # noqa: E402
from gate import GateState, decide_tick, note_asked  # noqa: E402
from mvp import DEFAULT_MODEL, ENV_KEY, decide, is_timeout, make_client  # noqa: E402
from postfilter import SPEAKS, enforce  # noqa: E402

LOGS = HERE / "live_logs"
SUMMARY_EVERY_S = 30.0


class LiveInitiator(Node):
    def __init__(self, args):
        super().__init__("live_initiator")
        self.args = args
        self.model = args.model or DEFAULT_MODEL[args.provider]
        self.client = make_client(args.provider, args.timeout)
        self.tts = None
        if args.speak:
            from tts import from_env
            self.tts = from_env()

        self.mem = Memory()
        self.gate = GateState()
        self.gate_cfg = {"max_stale_sec": args.stale_sec}
        self.lock = threading.Lock()
        self.busy = False
        self.latest = None
        self.bad_ctx_logged = 0.0

        self.create_subscription(String, "/social_context", self._on_context, 10)
        self.pub_decision = self.create_publisher(String, "/initiation_decision", 10)
        self.pub_engaged = self.create_publisher(Bool, "/engaged", 10) if (args.speak or args.engaged) else None
        self.pub_speaking = self.create_publisher(Bool, "/robot_speaking", 10) if args.speak else None
        if args.engaged:
            self.mem.engaged = True

        self.create_timer(1.0 / args.rate, self._tick)
        if self.pub_engaged:
            self.create_timer(1.0, self._publish_engaged)
        self.create_timer(SUMMARY_EVERY_S, self._summary)

        LOGS.mkdir(exist_ok=True)
        self.log_path = LOGS / f"{datetime.date.today().isoformat()}.jsonl"
        mode = "speak" if args.speak else "dry run" + (" (engaged)" if args.engaged else "")
        self.get_logger().info(f"{mode}: {args.provider} {self.model}, {args.rate:g} Hz, log {self.log_path}")

    def _on_context(self, msg):
        try:
            self.latest = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def _publish_engaged(self):
        self.pub_engaged.publish(Bool(data=self.args.engaged or self.mem.engaged))

    def _tick(self):
        if self.busy or self.latest is None:
            return
        now = time.time()
        with self.lock:
            ctx = fusion_to_context(self.latest, self.mem, now)
            if self.args.engaged:
                self.mem.engaged = True
                ctx["robot"]["engaged"] = True
        try:
            validate(ctx)
        except ValueError as e:
            if now - self.bad_ctx_logged > 5.0:
                self.get_logger().error(f"invalid context, skipped: {e}")
                self.bad_ctx_logged = now
            return
        ok, reason = decide_tick(ctx, self.gate, self.gate_cfg)
        if not ok:
            return
        note_asked(self.gate, ctx, now)
        with self.lock:
            pending, end = self.mem.pending, self.mem.last_utterance_end
            consume_pending(self.mem)
        # When the person stopped talking, and when this node first saw the words.
        heard_at = {"end": end, "seen": pending["t"]} if pending and end else None
        self.busy = True
        threading.Thread(target=self._decide, args=(ctx, heard_at), daemon=True).start()

    def _decide(self, ctx, heard_at=None):
        try:
            self._decide_once(ctx, heard_at)
        finally:
            self.busy = False

    def _decide_once(self, ctx, heard_at=None):
        out = {"t": ctx["t"], "provider": self.args.provider, "model": self.model}
        try:
            r = decide(self.args.provider, self.client, self.model, ctx, 6)
        except Exception as e:  # noqa: BLE001 - any failure means silence
            error = "TIMEOUT" if is_timeout(e) else str(e)[:300] or type(e).__name__
            out.update(action_final="remain_silent", error=error)
            self.get_logger().warning(f"LLM call failed, staying silent: {error}")
            self._publish(ctx, out)
            return

        final, blocked_by = enforce(ctx, r.action)
        speech = r.speech if (r.speech and final in SPEAKS) else None
        reason = blocked_by or (r.decision or {}).get("rule_fired")
        out.update(action_raw=r.action, action_final=final, blocked_by=blocked_by,
                   decision=r.decision, speech=speech.model_dump() if speech else None,
                   speech_error=r.speech_error, ms1=r.ms1, ms2=r.ms2)
        self._publish(ctx, out)

        heard = ((ctx.get("target") or {}).get("speech") or {}).get("partial_transcript")
        line = speech.text if speech else None
        self.get_logger().info(
            f"{final:<13} {reason or ''!s:<32} {r.ms1:5.0f} ms"
            + (f"  heard {heard!r}" if heard else "")
            + (f"  says {line!r}" if line else "")
            + (f"  (model said {r.action}, blocked)" if blocked_by else ""))

        if speech and self.tts:
            self._say(speech, r, heard_at)
        elif speech:
            self._log_timing(r, heard_at, None)
        with self.lock:
            apply_result(self.mem, final, reason, line, time.time())

    def _say(self, speech, r=None, heard_at=None):
        self.mem.speaking = True
        self.pub_speaking.publish(Bool(data=True))
        try:
            from tts import play
            start = time.time()
            path, _ = self.tts.synthesize(speech)
            if r is not None:
                self._log_timing(r, heard_at, time.time() - start)
            play(path)
        except Exception as e:  # noqa: BLE001 - a TTS failure must not stop the node
            self.get_logger().error(f"TTS failed: {e}")
        finally:
            self.pub_speaking.publish(Bool(data=False))
            self.mem.speaking = False

    def _log_timing(self, r, heard_at, tts_s):
        parts = []
        if heard_at:
            parts.append(f"heard {heard_at['seen'] - heard_at['end']:.1f} s")
        parts.append(f"decide {r.ms1 / 1000:.1f} s")
        if r.ms2:
            parts.append(f"line {r.ms2 / 1000:.1f} s")
        if tts_s is not None:
            parts.append(f"speech {tts_s:.1f} s")
        total = ""
        if heard_at:
            what = "starts talking" if tts_s is not None else "has its line"
            total = f"  ->  robot {what} {time.time() - heard_at['end']:.1f} s after the person stopped"
        self.get_logger().info("timing: " + ", ".join(parts) + total)

    def _publish(self, ctx, out):
        self.pub_decision.publish(String(data=json.dumps(out)))
        with open(self.log_path, "a") as f:
            f.write(json.dumps({"context": ctx, "result": out}) + "\n")

    def _summary(self):
        g = self.gate
        if g.ticks_seen:
            self.get_logger().info(
                f"gate: {g.asks} asks / {g.ticks_seen} ticks, "
                f"{g.suppression_rate:.0%} suppressed {g.suppressions}")

    def stop(self):
        if self.pub_speaking:
            self.pub_speaking.publish(Bool(data=False))
        if self.pub_engaged:
            self.pub_engaged.publish(Bool(data=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--provider", default="groq", choices=sorted(DEFAULT_MODEL))
    ap.add_argument("--model", default=None, help="overrides the provider default")
    ap.add_argument("--rate", type=float, default=3.0, help="ticks per second")
    ap.add_argument("--timeout", type=float, default=8.0, help="seconds per LLM call")
    ap.add_argument("--stale-sec", type=float, default=30.0,
                    help="re-ask after this long even if nothing changed")
    ap.add_argument("--engaged", action="store_true",
                    help="dry run with /engaged true, so the audio node transcribes")
    ap.add_argument("--speak", action="store_true",
                    help="say the line with tts.py and publish /robot_speaking and /engaged")
    args = ap.parse_args()
    if not os.environ.get(ENV_KEY[args.provider]):
        sys.exit(f"{ENV_KEY[args.provider]} is not set in {HERE / '.env'}")

    rclpy.init()
    node = LiveInitiator(args)
    stopped = (KeyboardInterrupt, getattr(executors, "ExternalShutdownException", KeyboardInterrupt))
    try:
        rclpy.spin(node)
    except stopped:
        pass
    finally:
        node.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
