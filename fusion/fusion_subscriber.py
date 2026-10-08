#!/usr/bin/env python3
"""Subscribe to /social_context and print what arrives.

Once each second it prints how many messages arrived in that second, then the
newest audio and vision messages with their ages. 10 messages each second
means the publisher runs at full rate.

    python3 ~/fri2_f26/fusion/fusion_subscriber.py          one summary each second
    python3 ~/fri2_f26/fusion/fusion_subscriber.py --all    every message, as it arrives

The script connects to ROS the same way as the audio and vision run scripts.
It loads ROS 2 Humble if the terminal has not, and sets ROS_LOCALHOST_ONLY=1.
"""

import json
import os
import sys

# Every node on flexo must use the same value, or the nodes cannot see each other.
os.environ["ROS_LOCALHOST_ONLY"] = "1"
try:
    import rclpy
    from std_msgs.msg import String
except ImportError as error:
    # ROS is not loaded in this terminal. Start again inside a shell that loads it.
    if os.environ.get("FUSION_ROS_LOADED"):
        sys.exit(f"ROS 2 does not load, even after /opt/ros/humble/setup.bash: {error}")
    os.environ["FUSION_ROS_LOADED"] = "1"
    os.execvp("bash", ["bash", "-c", 'source /opt/ros/humble/setup.bash && exec python3 "$0" "$@"',
                       os.path.abspath(__file__), *sys.argv[1:]])


def show(msg):
    for name in ("audio", "vision"):
        age = msg.get(f"{name}_age_s")
        age = "nothing yet" if age is None else f"{age:.1f} s old"
        print(f"  {name:<6} ({age}) {json.dumps(msg.get(name)) if msg.get(name) else ''}")


def main():
    every = "--all" in sys.argv
    rclpy.init()
    node = rclpy.create_node("fusion_subscriber")
    state = {"newest": None, "count": 0}

    def on_message(msg):
        data = json.loads(msg.data)
        state["newest"] = data
        state["count"] += 1
        if every:
            show(data)
            print("-" * 60, flush=True)

    def summary():
        if state["newest"] is None:
            print("waiting for /social_context", flush=True)
            return
        print(f"{state['count']} messages in the last second")
        show(state["newest"])
        print("-" * 60, flush=True)
        state["count"] = 0

    node.create_subscription(String, "/social_context", on_message, 10)
    if not every:
        node.create_timer(1.0, summary)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
