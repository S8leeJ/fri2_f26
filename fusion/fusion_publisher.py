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
DRIVER_TIMEOUT_S = 30.0

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
    proc = subprocess.Popen(["bash", str(script)], stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    say(f"{name}: started, output in {LOGS / (name + '.log')}")
    return proc


def log_tail(name, lines=8):
    text = (LOGS / f"{name}.log").read_text(errors="ignore").splitlines()
    return "\n".join("    " + line for line in text[-lines:])


def wait_for_text(name, proc, text, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            return False
        if text in (LOGS / f"{name}.log").read_text(errors="ignore"):
            return True
        time.sleep(0.5)
    return False


def stop(name, proc):
    if proc.poll() is not None:
        return
    say(f"{name}: stopping")
    for sig, wait_s in ((signal.SIGINT, 10), (signal.SIGTERM, 5), (signal.SIGKILL, 2)):
        try:
            os.killpg(proc.pid, sig)
            proc.wait(timeout=wait_s)
            return
        except subprocess.TimeoutExpired:
            continue
        except ProcessLookupError:
            return


def start_programs(started):
    """Start what does not run yet. Returns False if the driver does not start."""
    for name in ("audio", "driver"):
        if already_runs(name):
            say(f"{name}: already runs, using it")
        else:
            started[name] = start(name)

    if "driver" in started:
        say("waiting for the Kinect driver to say K4A Started")
        if not wait_for_text("driver", started["driver"], "K4A Started", DRIVER_TIMEOUT_S):
            say("the Kinect driver did not start. Its last lines:")
            print(log_tail("driver"), flush=True)
            return False
        say("Kinect started")

    if already_runs("pipeline"):
        say("pipeline: already runs, using it")
    else:
        started["pipeline"] = start("pipeline")
    return True


def publish(started):
    rclpy.init()
    node = rclpy.create_node("fusion_publisher")
    latest = {"audio": (None, None), "vision": (None, None)}
    pub = node.create_publisher(String, "/social_context", 10)

    def keep(name):
        def callback(msg):
            try:
                latest[name] = (json.loads(msg.data), time.time())
            except json.JSONDecodeError:
                pass
        return callback

    def send():
        now = time.time()
        out = {"t": now}
        for name, (data, received) in latest.items():
            out[name] = data
            out[f"{name}_age_s"] = None if received is None else round(now - received, 2)
        pub.publish(String(data=json.dumps(out)))

    reported = set()

    def status():
        now = time.time()
        parts = []
        for name, (data, received) in latest.items():
            parts.append(f"{name} " + ("nothing yet" if received is None else f"{now - received:.1f} s old"))
        vision = latest["vision"][0]
        if vision is not None:
            parts.append(f"people {vision.get('person_count')}")
        say("publishing /social_context at 10 Hz | " + " | ".join(parts))
        for name, proc in started.items():
            if proc.poll() is not None and name not in reported:
                reported.add(name)
                say(f"{name} stopped. Its last lines:")
                print(log_tail(name), flush=True)

    node.create_subscription(String, "/audio_context", keep("audio"), 10)
    node.create_subscription(String, "/hri/vision/context", keep("vision"), 10)
    node.create_timer(1.0 / RATE_HZ, send)
    node.create_timer(5.0, status)
    say(f"publishing /social_context at {RATE_HZ:.0f} Hz. Press Ctrl+C to stop.")
    # Ctrl+C ends spin with KeyboardInterrupt, or with ExternalShutdownException
    # in newer rclpy versions.
    stopped = (KeyboardInterrupt, getattr(executors, "ExternalShutdownException", KeyboardInterrupt))
    try:
        rclpy.spin(node)
    except stopped:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main():
    started = {}
    try:
        if start_programs(started):
            publish(started)
    except KeyboardInterrupt:
        pass
    finally:
        for name in ("pipeline", "audio", "driver"):
            if name in started:
                stop(name, started[name])


if __name__ == "__main__":
    main()
