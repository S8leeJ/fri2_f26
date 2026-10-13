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
ask, and one worker thread at a time calls the LLM and the post-filter.

Each reply to speech logs one "turn N:" line with the seconds for each step
(turn_trace.py). Ctrl+C prints the median and max of each step for the session.

Logs go to fusion/logs/, and each start clears them: decision.log (the terminal
lines), decisions.jsonl (each LLM call), and trace.jsonl (each reply's steps).
Each LLM call also goes to live_logs/<date>.jsonl, which keeps the whole day.
There, each start adds one "run_start" line, and each call has its run number.
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
import httpx

HERE = pathlib.Path(__file__).resolve().parent
dotenv.load_dotenv(HERE / ".env")

from context import validate  # noqa: E402
from fusion_adapter import Memory, apply_result, consume_pending, fusion_to_context  # noqa: E402
from gate import GateState, decide_tick, note_asked  # noqa: E402
from mvp import DEFAULT_MODEL, ENV_KEY, decide, is_timeout, make_client, reply_writers  # noqa: E402
from postfilter import SPEAKS, enforce  # noqa: E402
from turn_trace import Tracer  # noqa: E402

# Optional: turn toward the person (attention/ at the repo root). Without that folder,
# or with --turn-off, this node runs the same and never moves the robot.
sys.path.insert(0, str(HERE.parent.parent / "attention"))
try:
    import turn_to_person  # noqa: E402
except ImportError:
    turn_to_person = None
SUMMARY_EVERY_S = 30.0
# This run only, next to the audio and vision logs. Each start clears them.
RUN_LOGS = HERE.parent.parent / "fusion" / "logs"
# The whole day, all runs.
LOGS = HERE / "live_logs"


class _TeeLogger:
    """Sends each line to the ROS log and to fusion/logs/decision.log."""

    def __init__(self, logger, file):
        self._logger, self._file = logger, file

    def _line(self, level, msg):
        self._file.write(datetime.datetime.now().strftime("%H:%M:%S") + " " + level + " " + msg + chr(10))

    def info(self, msg, **kwargs):
        self._logger.info(msg, **kwargs)
        self._line("INFO", msg)

    def warning(self, msg, **kwargs):
        self._logger.warning(msg, **kwargs)
        self._line("WARN", msg)

    def error(self, msg, **kwargs):
        self._logger.error(msg, **kwargs)
        self._line("ERROR", msg)

    def __getattr__(self, name):
        return getattr(self._logger, name)


class LiveInitiator(Node):
    def __init__(self, args):
        super().__init__("live_initiator")
        RUN_LOGS.mkdir(parents=True, exist_ok=True)
        self.run_log = open(RUN_LOGS / "decision.log", "w", buffering=1)
        self.run_jsonl = open(RUN_LOGS / "decisions.jsonl", "w", buffering=1)
        (RUN_LOGS / "trace.jsonl").write_text("")
        self._tee = _TeeLogger(super().get_logger(), self.run_log)
        self.args = args
        self.model = args.model or DEFAULT_MODEL[args.provider]
        self.client = make_client(args.provider, args.timeout)
        self.tts = None
        if args.speak:
            from tts import from_env
            self.tts = from_env()

        self.mem = Memory()
        self.gate = GateState()
        self.gate_cfg = {"max_stale_sec": args.stale_sec, "settle_dwell_s": args.settle_dwell,
                         "settle_gaze_s": args.settle_gaze,
                         "settle_max_distance_m": args.greet_distance}
        self.lock = threading.Lock()
        self.busy = False
        self.latest = None
        self.bad_ctx_logged = 0.0
        # stt_done of the newest audio trace, and when this node first received it.
        self.trace_arrived = (None, None)

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

        self.tracer = Tracer(RUN_LOGS / "trace.jsonl")
        LOGS.mkdir(exist_ok=True)
        self.log_path = LOGS / f"{datetime.date.today().isoformat()}.jsonl"
        self.run = self._mark_run_start()
        mode = "speak" if args.speak else "dry run" + (" (engaged)" if args.engaged else "")
        self.get_logger().info(f"{mode}: {args.provider} {self.model}, {args.rate:g} Hz, "
                               f"run {self.run} of {self.log_path.name}, logs {RUN_LOGS}")
        self.turn = self._start_turning()
        self._warm_up()

    def _start_turning(self):
        if not self.args.speak:
            return None
        if self.args.turn_off:
            self.get_logger().info("turning: off (--turn-off)")
            return None
        if turn_to_person is None:
            self.get_logger().info("turning: off, attention/turn_to_person.py not found")
            return None
        options = turn_to_person.build_parser().parse_args(["--dry-run"] if self.args.turn_dry_run else [])
        self.get_logger().info("turning: " + ("dry run, prints only" if options.dry_run else
                                              "on, moves only when the base sends /odom"))
        return turn_to_person.TurnToPerson(self, options)

    def _warm_up(self):
        """Make the clients and open their connections now, not during the first reply."""
        start = time.time()
        clients = [self.client]
        if self.args.provider == "jev":
            clients += [client for _, client, _ in reply_writers()]
        if self.tts is not None:
            clients.append(self.tts.client)
        opened = 0
        for client in clients:
            if isinstance(client, httpx.Client):
                try:
                    client.get("/")    # any answer leaves the connection open
                    opened += 1
                except Exception:  # noqa: BLE001 - the first real call opens it instead
                    pass
        self.get_logger().info(f"warm-up: {opened} connections open in {time.time() - start:.1f} s")

    def _on_context(self, msg):
        try:
            self.latest = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        done = ((self.latest.get("audio") or {}).get("trace") or {}).get("stt_done")
        if done is not None and done != self.trace_arrived[0]:
            self.trace_arrived = (done, time.time())
            # A new transcript: check the gate now, not on the next tick.
            self._tick()

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
        heard_at = self._marks(pending, end, now) if pending and end else None
        self.busy = True
        threading.Thread(target=self._decide, args=(ctx, heard_at), daemon=True).start()

    def _marks(self, pending, end, asked):
        """Wall times for the steps from the end of speech to the LLM call."""
        marks = {"speech_end": end}
        trace = pending.get("trace") or {}
        if trace:
            marks.update({k: trace[k] for k in ("speech_end", "closed", "stt_done", "built") if k in trace})
            if self.trace_arrived[0] == trace.get("stt_done"):
                marks["arrived"] = self.trace_arrived[1]
        marks["seen"] = pending["t"]
        marks["asked"] = asked
        return marks

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
            + (f"  (model said {r.action}, blocked)" if blocked_by else "")
            + (f"  no line: {r.speech_error}" if r.speech_error and not line else ""))

        if speech and self.tts:
            self._say(speech, r, heard_at)
        elif speech:
            self._trace(r, heard_at, None)
        with self.lock:
            apply_result(self.mem, final, reason, line, time.time())

    def _say(self, speech, r=None, heard_at=None):
        self.mem.speaking = True
        self.pub_speaking.publish(Bool(data=True))
        start = time.time()

        def first_sound():
            if r is not None:
                self._trace(r, heard_at, time.time() - start)

        try:
            # A new line starts to play while it is still being made.
            self.tts.speak(speech, on_start=first_sound)
        except Exception as e:  # noqa: BLE001 - a TTS failure must not stop the node
            self.get_logger().error(f"TTS failed: {e}")
        finally:
            self.pub_speaking.publish(Bool(data=False))
            self.mem.speaking = False

    def _trace(self, r, heard_at, tts_s):
        # Only replies to speech have a start point.
        if heard_at:
            self.get_logger().info(self.tracer.add(heard_at, r.ms1, r.ms2, tts_s, time.time()))

    def get_logger(self):
        return getattr(self, "_tee", None) or super().get_logger()

    def _publish(self, ctx, out):
        self.pub_decision.publish(String(data=json.dumps(out)))
        self.run_jsonl.write(json.dumps({"context": ctx, "result": out}) + chr(10))
        with open(self.log_path, "a") as f:
            f.write(json.dumps({"run": self.run, "context": ctx, "result": out}) + chr(10))

    def _mark_run_start(self) -> int:
        try:
            run = self.log_path.read_text().count('"run_start"') + 1
        except FileNotFoundError:
            run = 1
        mark = {"run_start": datetime.datetime.now().isoformat(timespec="seconds"), "run": run,
                "provider": self.args.provider, "model": self.model, "speak": self.args.speak}
        with open(self.log_path, "a") as f:
            f.write(json.dumps(mark) + chr(10))
        return run

    def _summary(self):
        g = self.gate
        if g.ticks_seen:
            self.get_logger().info(
                f"gate: {g.asks} asks / {g.ticks_seen} ticks, "
                f"{g.suppression_rate:.0%} suppressed {g.suppressions}")

    def stop(self):
        summary = self.tracer.summary()
        print(summary, flush=True)
        self.run_log.write(summary + chr(10))
        if self.turn is not None:
            self.turn.stop()
        for pub in (self.pub_speaking, self.pub_engaged):
            if pub:
                try:
                    pub.publish(Bool(data=False))
                except Exception:  # noqa: BLE001 - ROS may already be shut down
                    pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--provider", default="groq", choices=sorted(DEFAULT_MODEL))
    ap.add_argument("--model", default=None, help="overrides the provider default")
    ap.add_argument("--rate", type=float, default=10.0, help="ticks per second, the same rate as fusion")
    ap.add_argument("--timeout", type=float, default=8.0, help="seconds per LLM call")
    ap.add_argument("--greet-distance", type=float, default=1.5,
                    help="meters: nobody farther away is greeted; 0 turns it off")
    ap.add_argument("--settle-dwell", type=float, default=2.0,
                    help="seconds a person must be in view before the LLM is asked; 0 turns it off")
    ap.add_argument("--settle-gaze", type=float, default=1.0,
                    help="seconds a person must look at the robot before the LLM is asked; 0 turns it off")
    ap.add_argument("--stale-sec", type=float, default=30.0,
                    help="re-ask after this long even if nothing changed")
    ap.add_argument("--engaged", action="store_true",
                    help="dry run with /engaged true, so the audio node transcribes")
    ap.add_argument("--speak", action="store_true",
                    help="say the line with tts.py and publish /robot_speaking and /engaged")
    ap.add_argument("--turn-off", action="store_true",
                    help="never turn the robot (attention/turn_to_person.py)")
    ap.add_argument("--turn-dry-run", action="store_true",
                    help="print the turns that attention/turn_to_person.py would make, do not move")
    args = ap.parse_args()
    if not os.environ.get(ENV_KEY[args.provider]):
        sys.exit(f"{ENV_KEY[args.provider]} is not set in {HERE / '.env'}")

    try:
        from rclpy.signals import SignalHandlerOptions
        # Ctrl+C then leaves ROS running until stop() has sent the last false values.
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    except (ImportError, TypeError):
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
