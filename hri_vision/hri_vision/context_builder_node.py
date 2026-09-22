import json
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .common import safe_json_loads


class ContextBuilderNode(Node):
    def __init__(self):
        super().__init__("context_builder_node")

        self.declare_parameter("person_context_topic", "/hri/vision/person_context")
        self.declare_parameter("orientation_topic", "/hri/vision/orientation")
        self.declare_parameter("output_topic", "/hri/vision/context")
        self.declare_parameter("orientation_max_age_s", 1.0)
        self.declare_parameter("log_context", True)
        self.declare_parameter("log_rate_hz", 1.0)

        self.latest_orientation_by_id = {}
        self.latest_orientation_time = 0.0
        self.last_log_time = 0.0

        self.person_sub = self.create_subscription(
            String,
            str(self.get_parameter("person_context_topic").value),
            self._on_person_context,
            10,
        )
        self.orientation_sub = self.create_subscription(
            String,
            str(self.get_parameter("orientation_topic").value),
            self._on_orientation,
            10,
        )
        self.publisher = self.create_publisher(
            String, str(self.get_parameter("output_topic").value), 10
        )

        self.get_logger().info(
            f"Context builder ready -> {self.get_parameter('output_topic').value}"
        )

    def _on_orientation(self, msg: String):
        data = safe_json_loads(msg.data)
        if data is None:
            return
        self.latest_orientation_by_id = {
            int(p["id"]): p
            for p in data.get("people", [])
            if isinstance(p, dict) and "id" in p
        }
        self.latest_orientation_time = time.monotonic()

    def _on_person_context(self, msg: String):
        data = safe_json_loads(msg.data)
        if data is None:
            return

        orientation_is_fresh = (
            time.monotonic() - self.latest_orientation_time
            <= float(self.get_parameter("orientation_max_age_s").value)
        )

        people = []
        for person in data.get("people", []):
            merged = dict(person)
            track_id = int(person.get("id", -1))

            orientation = (
                self.latest_orientation_by_id.get(track_id)
                if orientation_is_fresh
                else None
            )

            if orientation:
                merged["orientation"] = orientation.get("orientation", "unknown")
                merged["gaze"] = orientation.get("gaze", "unknown")
                merged["face_visible"] = orientation.get("face_visible")
            else:
                merged["orientation"] = "unknown"
                merged["gaze"] = "unknown"
                merged["face_visible"] = None

            # Bounding boxes are useful internally but not needed by the LLM.
            merged.pop("bbox", None)
            people.append(merged)

        payload = {
            "person_count": len(people),
            "people": people,
            "sensor_status": {
                "depth_fresh": bool(data.get("depth_fresh", False)),
                "orientation_fresh": orientation_is_fresh,
            },
        }

        out = String()
        out.data = json.dumps(payload, separators=(",", ":"))
        self.publisher.publish(out)

        if bool(self.get_parameter("log_context").value):
            log_rate = max(0.1, float(self.get_parameter("log_rate_hz").value))
            now = time.monotonic()
            if now - self.last_log_time >= 1.0 / log_rate:
                self.last_log_time = now
                self.get_logger().info(out.data)


def main(args=None):
    rclpy.init(args=args)
    node = ContextBuilderNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
