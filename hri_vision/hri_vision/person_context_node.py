import json
from collections import defaultdict, deque

import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .common import classify_direction, median_distance_mm, now_float, safe_json_loads


class PersonContextNode(Node):
    def __init__(self):
        super().__init__("person_context_node")

        self.declare_parameter("depth_topic", "/camera/aligned_depth_to_color/image_raw")
        self.declare_parameter("detections_topic", "/hri/vision/detections")
        self.declare_parameter("output_topic", "/hri/vision/person_context")
        self.declare_parameter("center_crop_fraction", 0.60)
        self.declare_parameter("min_depth_mm", 250)
        self.declare_parameter("max_depth_mm", 8000)
        self.declare_parameter("direction_threshold_mm", 100.0)
        self.declare_parameter("distance_window", 4)
        self.declare_parameter("track_grace_s", 2.0)
        self.declare_parameter("max_depth_age_s", 0.25)

        self.bridge = CvBridge()
        self.latest_depth = None
        self.latest_depth_time = None

        self.first_seen = {}
        self.last_seen = {}
        self.distance_history = defaultdict(lambda: deque(maxlen=4))

        self.depth_sub = self.create_subscription(
            Image,
            str(self.get_parameter("depth_topic").value),
            self._on_depth,
            10,
        )
        self.detection_sub = self.create_subscription(
            String,
            str(self.get_parameter("detections_topic").value),
            self._on_detections,
            10,
        )
        self.publisher = self.create_publisher(
            String, str(self.get_parameter("output_topic").value), 10
        )

        self.get_logger().info(
            "Person context ready: aligned depth + tracked boxes -> distance/direction/dwell"
        )

    def _on_depth(self, msg: Image):
        try:
            depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
        except Exception as exc:
            self.get_logger().error(f"Depth conversion failed: {exc}")
            return

        if depth.ndim != 2:
            self.get_logger().warning(
                f"Expected single-channel depth image, received shape={depth.shape}"
            )
            return

        self.latest_depth = np.asarray(depth)
        self.latest_depth_time = now_float(self)

    def _on_detections(self, msg: String):
        data = safe_json_loads(msg.data)
        if data is None:
            self.get_logger().warning("Received invalid detections JSON")
            return

        current = now_float(self)
        grace_s = float(self.get_parameter("track_grace_s").value)

        # Update deque size dynamically if config changed.
        history_len = max(2, int(self.get_parameter("distance_window").value))
        for track_id in list(self.distance_history.keys()):
            if self.distance_history[track_id].maxlen != history_len:
                self.distance_history[track_id] = deque(
                    self.distance_history[track_id], maxlen=history_len
                )

        visible_ids = set()
        output_people = []

        depth_fresh = (
            self.latest_depth is not None
            and self.latest_depth_time is not None
            and current - self.latest_depth_time
            <= float(self.get_parameter("max_depth_age_s").value)
        )

        for person in data.get("people", []):
            try:
                track_id = int(person["id"])
                bbox = person["bbox"]
            except (KeyError, TypeError, ValueError):
                continue

            visible_ids.add(track_id)

            if track_id not in self.first_seen:
                self.first_seen[track_id] = current
            elif current - self.last_seen.get(track_id, current) > grace_s:
                # Same numerical ID returned after a real gap: start a new dwell episode.
                self.first_seen[track_id] = current
                self.distance_history[track_id].clear()

            self.last_seen[track_id] = current

            raw_distance = None
            smoothed_distance = None
            direction = "unknown"

            if depth_fresh:
                raw_distance = median_distance_mm(
                    self.latest_depth,
                    bbox,
                    float(self.get_parameter("center_crop_fraction").value),
                    int(self.get_parameter("min_depth_mm").value),
                    int(self.get_parameter("max_depth_mm").value),
                )

            history = self.distance_history[track_id]
            previous_smoothed = float(np.mean(history)) if history else None

            if raw_distance is not None:
                history.append(raw_distance)
                smoothed_distance = float(np.mean(history))
                if previous_smoothed is not None:
                    delta = smoothed_distance - previous_smoothed
                    direction = classify_direction(
                        delta,
                        float(self.get_parameter("direction_threshold_mm").value),
                    )
                else:
                    direction = "stationary"

            output_people.append(
                {
                    "id": track_id,
                    "bbox": bbox,
                    "confidence": person.get("confidence"),
                    "distance_m": (
                        round(smoothed_distance / 1000.0, 3)
                        if smoothed_distance is not None
                        else None
                    ),
                    "direction": direction,
                    "dwell_time_s": round(current - self.first_seen[track_id], 2),
                }
            )

        # Remove long-stale state to avoid the dictionary growing forever.
        stale_ids = [
            track_id
            for track_id, last in self.last_seen.items()
            if current - last > max(10.0, grace_s * 5.0)
        ]
        for track_id in stale_ids:
            self.first_seen.pop(track_id, None)
            self.last_seen.pop(track_id, None)
            self.distance_history.pop(track_id, None)

        payload = {
            "stamp": data.get("stamp"),
            "frame_id": data.get("frame_id"),
            "person_count": len(output_people),
            "depth_fresh": depth_fresh,
            "people": output_people,
        }

        out = String()
        out.data = json.dumps(payload, separators=(",", ":"))
        self.publisher.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = PersonContextNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
