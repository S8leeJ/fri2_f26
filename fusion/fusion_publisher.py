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
--no-base does not start it. Without the attention/ folder, it is skipped too.

Before it starts anything, it stops what earlier runs left running: an older
fusion_publisher.py, then the vision pipeline, the audio node, the Kinect driver,
and the BWI base. It does not stop live_node.py. If a program does not stop,
for example because another account runs it, it prints the owner and exits.
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

# name: (run script, pgrep pattern for a copy that runs from before)
# The patterns need "python" or a ROS command, so that an editor with the file open does not match.
PROGRAMS = {
    "audio": (REPO / "audio_signals_FRI_II/tools/run_node.sh", "python[0-9.]* .*audio_context[ /]node"),
    "driver": (REPO / "hri_vision/scripts/run_driver.sh", "azure_kinect_ros_driver"),
    "pipeline": (REPO / "hri_vision/scripts/run_pipeline.sh",
                 "ros2 launch hri_vision vision_pipeline|lib/hri_vision/[a-z_]+_node"),
    "base": (REPO / "attention/run_base.sh", "ros2 launch bwi_launch segbot_v2"),
}
# What to stop before a run, in this order, with the seconds to wait after Ctrl+C.
# An older fusion_publisher.py goes first: on Ctrl+C it stops its own programs.
OLD = [("older fusion_publisher.py", r"python[0-9.]* [^ ]*fusion_publisher\.py", 60),
       ("vision pipeline", PROGRAMS["pipeline"][1], 10),
       ("audio node", PROGRAMS["audio"][1], 10),
       ("Kinect driver", PROGRAMS["driver"][1], 10),
       ("BWI base", PROGRAMS["base"][1], 10)]


def say(text):
    print(f"[fusion] {text}", flush=True)


def find(pattern):
    out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout
    return [int(pid) for pid in out.split() if int(pid) not in (os.getpid(), os.getppid())]


def stop_old(pattern, wait_s):
    """Stop the matching processes and their process groups: Ctrl+C, then SIGTERM, then SIGKILL.

    Returns False if they still run after all three.
    """
    for sig, wait in ((signal.SIGINT, wait_s), (signal.SIGTERM, 5), (signal.SIGKILL, 2)):
        pids = find(pattern)
        if not pids:
            return True
        for pid in pids:
            try:
                group = os.getpgid(pid)
                if group in (0, 1, os.getpgrp()):
                    os.kill(pid, sig)
                else:
                    os.killpg(group, sig)
            except (ProcessLookupError, PermissionError):
                pass
        end = time.time() + wait
        while time.time() < end and find(pattern):
            time.sleep(0.2)
    return not find(pattern)


def stop_old_runs():
    for label, pattern, wait_s in OLD:
        if not find(pattern):
            continue
        if stop_old(pattern, wait_s):
            say(f"stopped the {label} that ran from before")
            continue
        pids = ",".join(str(pid) for pid in find(pattern))
        owners = subprocess.run(["ps", "-o", "user=,pid=,args=", "-p", pids],
                                capture_output=True, text=True).stdout
        print(f"❌ the {label} that ran from before does not stop:", flush=True)
        for line in owners.splitlines():
            print("    " + line[:150], flush=True)
        print("   If another account runs it, log that account out. Then start again.", flush=True)
        return False
    return True


def clear_logs():
    LOGS.mkdir(parents=True, exist_ok=True)
    for name in PROGRAMS:
        (LOGS / f"{name}.log").write_text("")


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


def ctrl_c(*_):
    raise KeyboardInterrupt


def check(node, started, label, program, what, ready, timeout, required=True):
    """Spin the node until ready() is true, then print a check mark.

    Raises StartFailed, after it prints the program's last log lines, when the
    program stops or the time runs out. A part that is not required prints a
    warning instead, and check returns False.
    """
    end = time.time() + timeout
    while time.time() < end:
        rclpy.spin_once(node, timeout_sec=0.2)
        if ready():
            print(f"✅ {label:<8} {what}", flush=True)
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
    def launch(name):
        started[name] = start(name)

    say(f"starting {'the base, ' if base is not None else ''}audio, driver, and vision. "
        f"Their output is in {LOGS}/")
    if base is not None:
        launch("base")             # the slowest to start, so it goes first
    launch("audio")
    launch("driver")
    check(node, started, "audio", "audio", "/audio_context arrives",
          lambda: latest["audio"][1] is not None, AUDIO_TIMEOUT_S)
    check(node, started, "driver", "driver", "K4A Started",
          lambda: log_has("driver", "K4A Started"), DRIVER_TIMEOUT_S)
    launch("pipeline")
    check(node, started, "vision", "pipeline", "/hri/vision/context arrives",
          lambda: latest["vision"][1] is not None, VISION_TIMEOUT_S)
    if base is not None:
        check(node, started, "base", "base", "/odom arrives",
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
    if not stop_old_runs():
        sys.exit(1)
    rclpy.init()
    # Closing the terminal sends SIGHUP. Treat it as Ctrl+C, so the programs stop too.
    signal.signal(signal.SIGHUP, ctrl_c)
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
    if base is not None and not PROGRAMS["base"][0].exists():
        say("no attention/run_base.sh, so the base is not started and the robot does not turn")
        base = None
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
        # The programs run in their own sessions, so only this loop stops them. A second
        # Ctrl+C here used to end the loop and leave them running, and the next start
        # then ran two of each.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        if started:
            say("stopping " + ", ".join(started) + ". This can take up to a minute. "
                "Do not press Ctrl+C again.")
        for name in ("pipeline", "audio", "driver", "base"):
            if name in started:
                stop(name, started[name])
        if started:
            say("all stopped")
        audio_log.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
