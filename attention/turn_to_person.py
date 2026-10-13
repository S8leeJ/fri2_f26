#!/usr/bin/env python3
"""Turn the robot toward the person it talks to, then turn back when the talk ends.

live_node.py --speak starts it in its own process, so it needs no terminal of its own.
It moves only when the BWI base runs, because it needs /odom. It also runs alone:

    python3 ~/fri2_f26/attention/turn_to_person.py --dry-run   # prints, does not move
    python3 ~/fri2_f26/attention/turn_to_person.py             # moves the robot

Topics:
    in   /engaged                       std_msgs/Bool     true while a conversation runs
    in   /hri/vision/person_context     std_msgs/String   people with bbox and distance
    in   /odom                          nav_msgs/Odometry robot heading
    out  /cmd_vel                       geometry_msgs/Twist  turn in place only

The person is the nearest one, as in fusion_adapter.py. turner.py holds the rules.
Ctrl+C sends a stop.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

# Must match the other nodes on flexo, or they cannot see each other.
os.environ["ROS_LOCALHOST_ONLY"] = "1"
try:
    import rclpy
    from rclpy import executors
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from std_msgs.msg import Bool, String
except ImportError as error:
    if os.environ.get("TURN_ROS_LOADED"):
        sys.exit(f"ROS 2 does not load, even after /opt/ros/humble/setup.bash: {error}")
    os.environ["TURN_ROS_LOADED"] = "1"
    os.execvp("bash", ["bash", "-c", 'source /opt/ros/humble/setup.bash && exec python3 "$0" "$@"',
                       os.path.abspath(__file__), *sys.argv[1:]])

from turner import Turner  # noqa: E402

ENGAGED_STALE_S = 3.0      # live_node.py sends /engaged once a second
VISION_STALE_S = 1.0
ODOM_STALE_S = 0.5
STICKY_M = 0.5             # keep the same person unless someone else is this much nearer


def yaw_deg(q) -> float:
    return math.degrees(math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z)))


def bearing_deg(bbox, width: int, hfov_deg: float) -> float:
    """Degrees from the image center to the box center. Positive is to the right."""
    focal = (width / 2.0) / math.tan(math.radians(hfov_deg / 2.0))
    center = (bbox[0] + bbox[2]) / 2.0
    return math.degrees(math.atan((center - width / 2.0) / focal))


def pick(people, current_id):
    near = [p for p in people if p.get("distance_m") is not None and p.get("bbox")]
    if not near:
        return None
    nearest = min(near, key=lambda p: p["distance_m"])
    for p in near:
        if p.get("id") == current_id and p["distance_m"] <= nearest["distance_m"] + STICKY_M:
            return p
    return nearest


class TurnToPerson:
    def __init__(self, node, args):
        self.node, self.args = node, args
        self.turner = Turner(speed=args.speed, deadband_deg=args.deadband, hold_s=args.hold,
                             stop_within_deg=args.stop_within, max_turn_deg=args.max_turn)
        self.engaged = (False, 0.0)
        self.people = ([], 0.0)
        self.yaw = (None, 0.0)
        self.target_id = None
        self.last_omega = 0.0
        self.stops_left = 0
        node.create_subscription(Bool, "/engaged", self._on_engaged, 10)
        node.create_subscription(String, args.topic, self._on_people, 10)
        node.create_subscription(Odometry, "/odom", self._on_odom, 10)
        self.pub = node.create_publisher(Twist, "/cmd_vel", 10)
        node.create_timer(0.05, self._tick)

    def _on_engaged(self, msg):
        self.engaged = (bool(msg.data), time.time())

    def _on_people(self, msg):
        try:
            self.people = (json.loads(msg.data).get("people", []), time.time())
        except json.JSONDecodeError:
            pass

    def _on_odom(self, msg):
        self.yaw = (yaw_deg(msg.pose.pose.orientation), time.time())

    def _tick(self):
        now = time.time()
        engaged = self.engaged[0] and now - self.engaged[1] < ENGAGED_STALE_S
        yaw = self.yaw[0] if now - self.yaw[1] < ODOM_STALE_S else None
        bearing = None
        if now - self.people[1] < VISION_STALE_S:
            person = pick(self.people[0], self.target_id)
            if person is not None:
                self.target_id = person.get("id")
                bearing = bearing_deg(person["bbox"], self.args.image_width, self.args.hfov)
                if self.args.flip:
                    bearing = -bearing

        omega, note = self.turner.update(now, engaged, bearing, yaw)
        if note:
            self.node.get_logger().info("turn: " + note + (" (dry run)" if self.args.dry_run else ""))
        if self.args.dry_run:
            return
        if omega != 0.0:
            self._send(omega)
            self.stops_left = 3
        elif self.stops_left > 0:
            # A few stops in a row, so the base does not keep the last turn speed.
            self._send(0.0)
            self.stops_left -= 1

    def _send(self, omega):
        msg = Twist()
        msg.angular.z = float(omega)
        self.pub.publish(msg)

    def stop(self):
        if self.args.dry_run:
            return
        for _ in range(3):
            try:
                self._send(0.0)
            except Exception:  # noqa: BLE001 - ROS may already be shut down
                pass


def build_parser() -> argparse.ArgumentParser:
    """The options. live_node.py uses the defaults."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print what it would do, do not move")
    ap.add_argument("--speed", type=float, default=0.1, help="turn speed to command, rad/s (default 0.1)")
    ap.add_argument("--deadband", type=float, default=12.0, help="degrees off center before a turn starts")
    ap.add_argument("--hold", type=float, default=1.0, help="seconds off center before a turn starts")
    ap.add_argument("--stop-within", type=float, default=4.0, help="stop when this many degrees off center")
    ap.add_argument("--max-turn", type=float, default=40.0, help="most degrees from the start heading")
    ap.add_argument("--hfov", type=float, default=90.0, help="camera field of view, degrees (Kinect 720P: 90)")
    ap.add_argument("--image-width", type=int, default=1280, help="camera image width in pixels")
    ap.add_argument("--flip", action="store_true", help="use if the dry run names the wrong side")
    ap.add_argument("--topic", default="/hri/vision/person_context")
    return ap


def main():
    args = build_parser().parse_args()

    try:
        from rclpy.signals import SignalHandlerOptions
        # Ctrl+C then leaves ROS running until stop() has sent the stop.
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    except (ImportError, TypeError):
        rclpy.init()
    node = rclpy.create_node("turn_to_person")
    turn = TurnToPerson(node, args)
    node.get_logger().info(
        f"{'dry run, not moving' if args.dry_run else 'moving'}: speed {args.speed} rad/s, "
        f"deadband {args.deadband} deg for {args.hold} s, stop within {args.stop_within} deg, "
        f"at most {args.max_turn} deg")
    stopped = (KeyboardInterrupt, getattr(executors, "ExternalShutdownException", KeyboardInterrupt))
    try:
        rclpy.spin(node)
    except stopped:
        pass
    finally:
        turn.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
