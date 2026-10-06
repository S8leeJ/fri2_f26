import json

import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


class DetectionNode(Node):
    def __init__(self):
        super().__init__("detection_node")

        self.declare_parameter("image_topic", "/camera/color/image_raw")
        self.declare_parameter("output_topic", "/hri/vision/detections")
        self.declare_parameter("model", "yolo11n.pt")
        self.declare_parameter("tracker", "bytetrack.yaml")
        self.declare_parameter("confidence", 0.35)
        self.declare_parameter("iou", 0.5)
        self.declare_parameter("device", "cpu")
        self.declare_parameter("max_rate_hz", 12.0)

        image_topic = self.get_parameter("image_topic").value
        output_topic = self.get_parameter("output_topic").value

        self.bridge = CvBridge()
        self.last_process_ns = 0

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "Ultralytics is not installed. Run: pip install ultralytics"
            ) from exc

        model_name = self.get_parameter("model").value
        self.get_logger().info(f"Loading YOLO model: {model_name}")
        self.model = YOLO(model_name)

        self.publisher = self.create_publisher(String, output_topic, 10)
        self.subscription = self.create_subscription(
            Image, image_topic, self._on_image, 10
        )

        self.get_logger().info(
            f"Detection ready: {image_topic} -> {output_topic}; "
            f"tracker={self.get_parameter('tracker').value}"
        )

    def _on_image(self, msg: Image):
        max_rate = float(self.get_parameter("max_rate_hz").value)
        now_ns = self.get_clock().now().nanoseconds
        if max_rate > 0:
            min_period_ns = int(1e9 / max_rate)
            if now_ns - self.last_process_ns < min_period_ns:
                return
        self.last_process_ns = now_ns

        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as exc:
            self.get_logger().error(f"RGB conversion failed: {exc}")
            return

        try:
            results = self.model.track(
                frame,
                persist=True,
                tracker=str(self.get_parameter("tracker").value),
                classes=[0],  # COCO person class only
                conf=float(self.get_parameter("confidence").value),
                iou=float(self.get_parameter("iou").value),
                device=str(self.get_parameter("device").value),
                verbose=False,
            )
        except Exception as exc:
            self.get_logger().error(f"YOLO tracking failed: {exc}")
            return

        people = []
        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            for box in boxes:
                if box.id is None:
                    # Detections without a tracker ID are not useful for dwell/motion.
                    continue
                track_id = int(box.id[0].item())
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                conf = float(box.conf[0].item()) if box.conf is not None else None
                people.append(
                    {
                        "id": track_id,
                        "bbox": [x1, y1, x2, y2],
                        "confidence": conf,
                    }
                )

        payload = {
            "stamp": {
                "sec": int(msg.header.stamp.sec),
                "nanosec": int(msg.header.stamp.nanosec),
            },
            "frame_id": msg.header.frame_id,
            "image_width": int(msg.width),
            "image_height": int(msg.height),
            "person_count": len(people),
            "people": people,
        }

        out = String()
        out.data = json.dumps(payload, separators=(",", ":"))
        self.publisher.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = DetectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
