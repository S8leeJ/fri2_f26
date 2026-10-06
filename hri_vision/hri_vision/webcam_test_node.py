import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image


class WebcamTestNode(Node):
    """Publishes webcam RGB plus synthetic aligned depth for pre-robot testing."""

    def __init__(self):
        super().__init__("webcam_test_node")

        self.declare_parameter("camera_index", 0)
        self.declare_parameter("rgb_topic", "/hri/test/rgb")
        self.declare_parameter("depth_topic", "/hri/test/depth")
        self.declare_parameter("synthetic_depth_mm", 2000)
        self.declare_parameter("fps", 10.0)

        index = int(self.get_parameter("camera_index").value)
        self.cap = cv2.VideoCapture(index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open webcam index {index}")

        self.bridge = CvBridge()
        self.rgb_pub = self.create_publisher(
            Image, str(self.get_parameter("rgb_topic").value), 10
        )
        self.depth_pub = self.create_publisher(
            Image, str(self.get_parameter("depth_topic").value), 10
        )

        fps = max(1.0, float(self.get_parameter("fps").value))
        self.timer = self.create_timer(1.0 / fps, self._tick)
        self.get_logger().warning(
            "WEB-CAM TEST MODE: depth is synthetic. Detection/orientation are real; "
            "distance and direction are only plumbing tests."
        )

    def _tick(self):
        ok, frame = self.cap.read()
        if not ok:
            self.get_logger().warning("Webcam frame read failed")
            return

        stamp = self.get_clock().now().to_msg()

        rgb_msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        rgb_msg.header.stamp = stamp
        rgb_msg.header.frame_id = "webcam"
        self.rgb_pub.publish(rgb_msg)

        depth_mm = int(self.get_parameter("synthetic_depth_mm").value)
        depth = np.full(frame.shape[:2], depth_mm, dtype=np.uint16)
        depth_msg = self.bridge.cv2_to_imgmsg(depth, encoding="16UC1")
        depth_msg.header.stamp = stamp
        depth_msg.header.frame_id = "webcam"
        self.depth_pub.publish(depth_msg)

    def destroy_node(self):
        try:
            self.cap.release()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = WebcamTestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
