import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory("hri_vision")
    config = os.path.join(package_share, "config", "vision.yaml")

    camera_backend = LaunchConfiguration("camera_backend")
    rgb_topic = LaunchConfiguration("rgb_topic")
    depth_topic = LaunchConfiguration("depth_topic")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "camera_backend",
                default_value="external",
                description="external | pyk4a | webcam",
            ),
            DeclareLaunchArgument(
                "rgb_topic",
                default_value="/camera/color/image_raw",
                description="RGB image topic consumed by the pipeline",
            ),
            DeclareLaunchArgument(
                "depth_topic",
                default_value="/camera/aligned_depth_to_color/image_raw",
                description="Aligned uint16 depth-in-mm topic consumed by the pipeline",
            ),

            # Optional camera sources. In normal robot operation use
            # camera_backend:=external and let the robot's camera driver publish.
            Node(
                package="hri_vision",
                executable="webcam_test_node",
                name="webcam_test_node",
                output="screen",
                parameters=[
                    config,
                    {"rgb_topic": rgb_topic, "depth_topic": depth_topic},
                ],
                condition=IfCondition(
                    PythonExpression(["'", camera_backend, "' == 'webcam'"])
                ),
            ),
            Node(
                package="hri_vision",
                executable="kinect_direct_node",
                name="kinect_direct_node",
                output="screen",
                parameters=[
                    config,
                    {"rgb_topic": rgb_topic, "depth_topic": depth_topic},
                ],
                condition=IfCondition(
                    PythonExpression(["'", camera_backend, "' == 'pyk4a'"])
                ),
            ),

            Node(
                package="hri_vision",
                executable="detection_node",
                name="detection_node",
                output="screen",
                emulate_tty=True,
                parameters=[config, {"image_topic": rgb_topic}],
            ),
            Node(
                package="hri_vision",
                executable="person_context_node",
                name="person_context_node",
                output="screen",
                emulate_tty=True,
                parameters=[config, {"depth_topic": depth_topic}],
            ),
            Node(
                package="hri_vision",
                executable="orientation_node",
                name="orientation_node",
                output="screen",
                emulate_tty=True,
                parameters=[config, {"image_topic": rgb_topic}],
            ),
            Node(
                package="hri_vision",
                executable="context_builder_node",
                name="context_builder_node",
                output="screen",
                emulate_tty=True,
                parameters=[config],
            ),
        ]
    )
