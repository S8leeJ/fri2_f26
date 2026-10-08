#!/usr/bin/env python3
"""Start the audio and vision programs, then publish both together on /social_context.

One command, in any terminal on flexo:

    python3 ~/fri2_f26/fusion/fusion_publisher.py

It starts these run scripts, in this order:

    audio_signals_FRI_II/tools/run_node.sh   audio node, publishes /audio_context
    hri_vision/scripts/run_driver.sh         Kinect driver
    hri_vision/scripts/run_pipeline.sh       vision pipeline, publishes /hri/vision/context
                                             (starts when the driver says "K4A Started")

A program that already runs is used as it is, and is not started again.
Each program writes its output to fusion/logs/<name>.log.

Then it publishes the newest audio and vision messages together, 10 times each second:

    {"t": 1791447072.3,
     "audio": {...the newest /audio_context message...},  "audio_age_s": 0.4,
     "vision": {...the newest /hri/vision/context message...}, "vision_age_s": 0.1}

The messages are copied without change. A source that has not sent anything
yet is null. A growing age shows a program that stopped.

It prints a check mark for each part when the part works: audio (the first
/audio_context message arrives), driver (K4A Started), vision (the first
/hri/vision/context message arrives), and publish. If a part does not work, it
prints a cross and the program's last log lines, then stops what it started.

After it says "Press Ctrl+C to stop", it prints nothing more. Each program's
output is in fusion/logs/, and a growing age in /social_context shows a program
that stopped.

Ctrl+C stops the programs that this script started: the pipeline and the audio
node first, the driver last.

Run the setup script in each folder once before you use this script. This
script does not install or check anything.
"""

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

# name: (run script, pgrep pattern that matches the program when it already runs)
PROGRAMS = {
    "audio": (REPO / "audio_signals_FRI_II/tools/run_node.sh", "audio_context[ /]node"),
    "driver": (REPO / "hri_vision/scripts/run_driver.sh", "azure_kinect_ros_driver"),
    "pipeline": (REPO / "hri_vision/scripts/run_pipeline.sh", r"vision_pipeline\.launch\.py"),
}


def say(text):
    print(f"[fusion] {text}", flush=True)


def already_runs(name):
    pattern = PROGRAMS[name][1]
    return subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0


def start(name):
    script = PROGRAMS[name][0]
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{name}.log", "w")
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


def check(node, started, reused, label, program, what, ready, timeout):
    """Spin the node until ready() is true, then print a check mark.

    Raises StartFailed, after it prints the program's last log lines, when the
    program stops or the time runs out.
    """
    end = time.time() + timeout
    while time.time() < end:
        rclpy.spin_once(node, timeout_sec=0.2)
        if ready():
            note = " (already running)" if program in reused else ""
            print(f"✅ {label:<8} {what}{note}", flush=True)
            return
        proc = started.get(program)
        if proc is not None and proc.poll() is not None:
            break
    print(f"❌ {label:<8} {what}: did not happen", flush=True)
    if program in started:
        print(f"   The last lines of {LOGS / (program + '.log')}:", flush=True)
        print(log_tail(program), flush=True)
    raise StartFailed()


def run(node, latest, started):
    reused = set()

    def launch(name):
        if already_runs(name):
            reused.add(name)
        else:
            started[name] = start(name)

    say(f"starting audio, driver, and vision. Their output is in {LOGS}/")
    launch("audio")
    launch("driver")
    check(node, started, reused, "audio", "audio", "/audio_context arrives",
          lambda: latest["audio"][1] is not None, AUDIO_TIMEOUT_S)
    check(node, started, reused, "driver", "driver", "K4A Started",
          lambda: "driver" in reused or log_has("driver", "K4A Started"), DRIVER_TIMEOUT_S)
    launch("pipeline")
    check(node, started, reused, "vision", "pipeline", "/hri/vision/context arrives",
          lambda: latest["vision"][1] is not None, VISION_TIMEOUT_S)

    pub = node.create_publisher(String, "/social_context", 10)

    def send():
        now = time.time()
        out = {"t": now}
        for name, (data, received) in latest.items():
            out[name] = data
            out[f"{name}_age_s"] = None if received is None else round(now - received, 2)
        pub.publish(String(data=json.dumps(out)))

    node.create_timer(1.0 / RATE_HZ, send)
    print(f"✅ {'publish':<8} /social_context at {RATE_HZ:.0f} Hz", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    rclpy.spin(node)


def main():
    rclpy.init()
    node = rclpy.create_node("fusion_publisher")
    latest = {"audio": (None, None), "vision": (None, None)}

    def keep(name):
        def callback(msg):
            try:
                latest[name] = (json.loads(msg.data), time.time())
            except json.JSONDecodeError:
                pass
        return callback

    node.create_subscription(String, "/audio_context", keep("audio"), 10)
    node.create_subscription(String, "/hri/vision/context", keep("vision"), 10)

    # Ctrl+C ends spin with KeyboardInterrupt, or with ExternalShutdownException
    # in newer rclpy versions.
    stopped = (KeyboardInterrupt, StartFailed,
               getattr(executors, "ExternalShutdownException", KeyboardInterrupt))
    started = {}
    try:
        run(node, latest, started)
    except stopped:
        pass
    finally:
        for name in ("pipeline", "audio", "driver"):
            if name in started:
                stop(name, started[name])
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
