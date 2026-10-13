#!/usr/bin/env python3
"""Start the audio and vision programs, then publish both together on /social_context.

One command, in any terminal on flexo:

    python3 ~/fri2_f26/fusion/fusion_publisher.py

It starts these run scripts, in this order:

    attention/run_base.sh                    BWI base: Segway, lasers, map, AMCL, no RViz.
                                             It gives /cmd_vel and /odom for turning.
    audio_signals_FRI_II/tools/run_node.sh   audio node, publishes /audio_context
    hri_vision/scripts/run_driver.sh         Kinect driver
    hri_vision/scripts/run_pipeline.sh       vision pipeline, publishes /hri/vision/context
                                             (starts when the driver says "K4A Started")

The base is optional. If /odom does not arrive, for example because the Segway is
off, it prints a warning and goes on: everything works except turning.
--no-base does not start it.

A program that already runs is used as it is, and is not started again.
Each run clears fusion/logs/ first. Each program writes its output to
fusion/logs/<name>.log. audio.log also gets every /audio_context message, one
JSON object per line. pipeline.log has the vision JSON.

Then it publishes the newest audio and vision messages together, 10 times each second.
It also publishes at once when a new audio message arrives:

    {"t": 1791447072.3,
     "audio": {...the newest /audio_context message...},  "audio_age_s": 0.4,
     "vision": {...the newest /hri/vision/context message...}, "vision_age_s": 0.1}

The messages are copied without change. A source that has not sent anything
yet is null. A growing age shows a program that stopped.

It prints a check mark for each part when the part works: audio (the first
/audio_context message arrives), driver (K4A Started), vision (the first
/hri/vision/context message arrives), base (the first /odom message arrives),
and publish. If a part does not work, it
prints a cross and the program's last log lines, then stops what it started.

After it says "Press Ctrl+C to stop", it prints nothing more. Each program's
output is in fusion/logs/, and a growing age in /social_context shows a program
that stopped.

Ctrl+C stops the programs that this script started: the pipeline and the audio
node first, then the driver, and the base last.

Run the setup script in each folder once before you use this script. This
script does not install or check anything.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Every node on flexo must use the same value, or the nodes cannot see each other.
# The programs that this script starts get the same value.
os.environ["ROS_LOCALHOST_ONLY"] = "1"
try:
    import rclpy
    from rclpy import executors
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String
except ImportError as error:
    # ROS is not loaded in this terminal. Start again inside a shell that loads it.
    if os.environ.get("FUSION_ROS_LOADED"):
        sys.exit(f"ROS 2 does not load, even after /opt/ros/humble/setup.bash: {error}")
    os.environ["FUSION_ROS_LOADED"] = "1"
    os.execvp("bash", ["bash", "-c", 'source /opt/ros/humble/setup.bash && exec python3 "$0" "$@"',
                       os.path.abspath(__file__), *sys.argv[1:]])

REPO = Path(__file__).resolve().parent.parent
LOGS = REPO / "fusion" / "logs"
RATE_HZ = 10.0
AUDIO_TIMEOUT_S = 60.0
DRIVER_TIMEOUT_S = 30.0
VISION_TIMEOUT_S = 60.0
BASE_TIMEOUT_S = 30.0      # after vision is ready; the base starts first

# name: (run script, pgrep pattern that matches the program when it already runs)
PROGRAMS = {
    "audio": (REPO / "audio_signals_FRI_II/tools/run_node.sh", "audio_context[ /]node"),
    "driver": (REPO / "hri_vision/scripts/run_driver.sh", "azure_kinect_ros_driver"),
    "pipeline": (REPO / "hri_vision/scripts/run_pipeline.sh", r"vision_pipeline\.launch\.py"),
    "base": (REPO / "attention/run_base.sh", r"segbot_v2\.launch\.py"),
}


def say(text):
    print(f"[fusion] {text}", flush=True)


def already_runs(name):
    pattern = PROGRAMS[name][1]
    return subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0


def clear_logs():
    LOGS.mkdir(parents=True, exist_ok=True)
    for name in PROGRAMS:
        (LOGS / f"{name}.log").write_text("")


def note(name, text):
    with open(LOGS / f"{name}.log", "a") as log:
        log.write(f"[fusion] {text}\n")


def start(name):
    script = PROGRAMS[name][0]
    # Append, so that the program's output and the audio JSON that this script
    # adds to audio.log do not write over each other.
    log = open(LOGS / f"{name}.log", "a")
    # A new session, so that Ctrl+C reaches only this script. It then stops
    # the programs in the right order.
    return subprocess.Popen(["bash", str(script)], stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)


def log_tail(name, lines=8):
    path = LOGS / f"{name}.log"
    text = path.read_text(errors="ignore").splitlines() if path.exists() else []
    return "\n".join("    " + line for line in text[-lines:])


def log_has(name, text):
    path = LOGS / f"{name}.log"
    return path.exists() and text in path.read_text(errors="ignore")


def stop(name, proc):
    if proc.poll() is not None:
        return
    for sig, wait_s in ((signal.SIGINT, 10), (signal.SIGTERM, 5), (signal.SIGKILL, 2)):
        try:
            os.killpg(proc.pid, sig)
            proc.wait(timeout=wait_s)
            return
        except subprocess.TimeoutExpired:
            continue
        except ProcessLookupError:
            return


class StartFailed(Exception):
    pass


def check(node, started, reused, label, program, what, ready, timeout, required=True):
    """Spin the node until ready() is true, then print a check mark.

    Raises StartFailed, after it prints the program's last log lines, when the
    program stops or the time runs out. A part that is not required prints a
    warning instead, and check returns False.
    """
    end = time.time() + timeout
    while time.time() < end:
        rclpy.spin_once(node, timeout_sec=0.2)
        if ready():
            note = " (already running)" if program in reused else ""
            print(f"✅ {label:<8} {what}{note}", flush=True)
            return True
        proc = started.get(program)
        if proc is not None and proc.poll() is not None:
            break
    if required:
        print(f"❌ {label:<8} {what}: did not happen", flush=True)
    else:
        print(f"⚠️  {label:<8} {what}: did not happen, so the robot will not turn", flush=True)
    if program in started:
        print(f"   The last lines of {LOGS / (program + '.log')}:", flush=True)
        print(log_tail(program), flush=True)
    if required:
        raise StartFailed()
    return False


def run(node, latest, started, sender, base):
    reused = set()

    def launch(name):
        if already_runs(name):
            reused.add(name)
            note(name, "This program ran before fusion started, so its output is not in this file.")
        else:
            started[name] = start(name)

    say(f"starting {'the base, ' if base is not None else ''}audio, driver, and vision. "
        f"Their output is in {LOGS}/")
    if base is not None:
        launch("base")             # the slowest to start, so it goes first
    launch("audio")
    launch("driver")
    check(node, started, reused, "audio", "audio", "/audio_context arrives",
          lambda: latest["audio"][1] is not None, AUDIO_TIMEOUT_S)
    check(node, started, reused, "driver", "driver", "K4A Started",
          lambda: "driver" in reused or log_has("driver", "K4A Started"), DRIVER_TIMEOUT_S)
    launch("pipeline")
    check(node, started, reused, "vision", "pipeline", "/hri/vision/context arrives",
          lambda: latest["vision"][1] is not None, VISION_TIMEOUT_S)
    if base is not None:
        check(node, started, reused, "base", "base", "/odom arrives",
              lambda: base["odom"], BASE_TIMEOUT_S, required=False)

    pub = node.create_publisher(String, "/social_context", 10)

    def send():
        now = time.time()
        out = {"t": now}
        for name, (data, received) in latest.items():
            out[name] = data
            out[f"{name}_age_s"] = None if received is None else round(now - received, 2)
        pub.publish(String(data=json.dumps(out)))

    node.create_timer(1.0 / RATE_HZ, send)
    sender["send"] = send
    print(f"✅ {'publish':<8} /social_context at {RATE_HZ:.0f} Hz", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    rclpy.spin(node)


def main():
    ap = argparse.ArgumentParser(description="Start audio, vision, and the base, then publish /social_context.")
    ap.add_argument("--no-base", action="store_true", help="do not start the BWI base, so the robot does not turn")
    args = ap.parse_args()
    rclpy.init()
    node = rclpy.create_node("fusion_publisher")
    latest = {"audio": (None, None), "vision": (None, None)}
    sender = {}
    clear_logs()
    audio_log = open(LOGS / "audio.log", "a", buffering=1)

    def keep(name, log=None):
        def callback(msg):
            try:
                latest[name] = (json.loads(msg.data), time.time())
            except json.JSONDecodeError:
                return
            if log is not None:
                log.write(msg.data + "\n")
            # Send new audio at once, so a transcript does not wait for the timer.
            if name == "audio" and "send" in sender:
                sender["send"]()
        return callback

    node.create_subscription(String, "/audio_context", keep("audio", audio_log), 10)
    node.create_subscription(String, "/hri/vision/context", keep("vision"), 10)
    base = None if args.no_base else {"odom": False}
    if base is not None:
        node.create_subscription(Odometry, "/odom", lambda msg: base.update(odom=True), 10)

    # Ctrl+C ends spin with KeyboardInterrupt, or with ExternalShutdownException
    # in newer rclpy versions.
    stopped = (KeyboardInterrupt, StartFailed,
               getattr(executors, "ExternalShutdownException", KeyboardInterrupt))
    started = {}
    try:
        run(node, latest, started, sender, base)
    except stopped:
        pass
    finally:
        for name in ("pipeline", "audio", "driver", "base"):
            if name in started:
                stop(name, started[name])
        audio_log.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
