import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image


class KinectDirectNode(Node):
    """
    Optional direct Azure Kinect publisher using pyk4a.

    This is useful if the robot does not already expose aligned ROS image topics.
    The native Azure Kinect Sensor SDK still has to be installed on the machine.
    """

    def __init__(self):
        super().__init__("kinect_direct_node")

        self.declare_parameter("rgb_topic", "/hri/kinect/rgb")
        self.declare_parameter("depth_topic", "/hri/kinect/depth")
        self.declare_parameter("fps", 15.0)

        try:
            from pyk4a import (
                Config,
                ColorResolution,
                DepthMode,
                FPS,
                PyK4A,
            )
        except ImportError as exc:
            raise RuntimeError(
                "pyk4a is not installed. Install the Azure Kinect Sensor SDK first, "
                "then run: pip install pyk4a"
            ) from exc

        requested_fps = int(round(float(self.get_parameter("fps").value)))
        fps_map = {5: FPS.FPS_5, 15: FPS.FPS_15, 30: FPS.FPS_30}
        fps_enum = fps_map.get(requested_fps, FPS.FPS_15)

        self.k4a = PyK4A(
            Config(
                color_resolution=ColorResolution.RES_720P,
                depth_mode=DepthMode.NFOV_UNBINNED,
                camera_fps=fps_enum,
                synchronized_images_only=True,
            )
        )
        self.k4a.start()

        self.bridge = CvBridge()
        self.rgb_pub = self.create_publisher(
            Image, str(self.get_parameter("rgb_topic").value), 10
        )
        self.depth_pub = self.create_publisher(
            Image, str(self.get_parameter("depth_topic").value), 10
        )

        self.timer = self.create_timer(1.0 / max(1, requested_fps), self._tick)
        self.get_logger().info("Azure Kinect direct capture started")

    def _tick(self):
        try:
            capture = self.k4a.get_capture()
        except Exception as exc:
            self.get_logger().error(f"Kinect capture failed: {exc}")
            return

        color = capture.color
        depth = capture.transformed_depth
        if color is None or depth is None:
            return

        # pyk4a color is typically BGRA; publish BGR for OpenCV/YOLO.
        if color.ndim == 3 and color.shape[2] == 4:
            color = cv2.cvtColor(color, cv2.COLOR_BGRA2BGR)

        stamp = self.get_clock().now().to_msg()

        rgb_msg = self.bridge.cv2_to_imgmsg(color, encoding="bgr8")
        rgb_msg.header.stamp = stamp
        rgb_msg.header.frame_id = "azure_kinect_color"
        self.rgb_pub.publish(rgb_msg)

        depth_msg = self.bridge.cv2_to_imgmsg(depth, encoding="16UC1")
        depth_msg.header.stamp = stamp
        depth_msg.header.frame_id = "azure_kinect_color"
        self.depth_pub.publish(depth_msg)

    def destroy_node(self):
        try:
            self.k4a.stop()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = KinectDirectNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
