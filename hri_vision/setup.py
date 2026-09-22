from glob import glob
import os

from setuptools import find_packages, setup

package_name = "hri_vision"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="HRI Team",
    maintainer_email="swathi@example.com",
    description="HRI vision pipeline for ROS 2",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "detection_node = hri_vision.detection_node:main",
            "person_context_node = hri_vision.person_context_node:main",
            "orientation_node = hri_vision.orientation_node:main",
            "context_builder_node = hri_vision.context_builder_node:main",
            "webcam_test_node = hri_vision.webcam_test_node:main",
            "kinect_direct_node = hri_vision.kinect_direct_node:main",
        ],
    },
)
