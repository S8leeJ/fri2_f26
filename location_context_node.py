"""
ROS2 node that listens to the robot's live position and turns it into
location context using get_location_context() from location_context.py.

Assumes the pose comes from AMCL on the /amcl_pose topic, as
geometry_msgs/msg/PoseWithCovarianceStamped. Confirm this matches your
setup with:
  ros2 topic list
  ros2 topic info /amcl_pose
If your topic or message type is different, update TOPIC_NAME and the
msg import/type below to match.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseWithCovarianceStamped

from location_context import get_location_context

TOPIC_NAME = "/amcl_pose"


class LocationContextNode(Node):
    def __init__(self):
        super().__init__("location_context_node")
        self.subscription = self.create_subscription(
            PoseWithCovarianceStamped,
            TOPIC_NAME,
            self.pose_callback,
            10,  # queue size
        )

    def pose_callback(self, msg: PoseWithCovarianceStamped):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y

        context = get_location_context(x, y)
        self.get_logger().info(f"Position ({x:.2f}, {y:.2f}) -> {context}")


def main():
    rclpy.init()
    node = LocationContextNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()