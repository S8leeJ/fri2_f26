#!/usr/bin/env bash
# Build the vision package, then start the pipeline. Start
# scripts/run_driver.sh first, in another terminal.
#
#   bash scripts/run_pipeline.sh
#
# The build runs every time, so the pipeline always uses the current code.
# The pipeline publishes JSON on /hri/vision/context. To see it, run
# scripts/view.sh in another terminal.

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(dirname "$PKG")"

source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1

cd "$REPO"
colcon build --symlink-install --packages-select hri_vision || {
    echo "❌ FAILED: the build did not finish. Run this, then try again: bash $PKG/scripts/setup_flexo.sh"
    exit 1
}
echo "✅ hri_vision built"
source "$REPO/install/setup.bash"

# An old ROS helper process can have other settings and miss the driver.
ros2 daemon stop > /dev/null 2>&1
found=""
for _ in 1 2 3 4 5; do
    if ros2 topic list 2> /dev/null | grep -qx /rgb/image_raw; then
        found=1
        break
    fi
    sleep 1
done
[ -n "$found" ] || {
    echo "❌ FAILED: no camera images on /rgb/image_raw. Start the driver first: bash $PKG/scripts/run_driver.sh"
    exit 1
}
echo "✅ Kinect driver found"

# YOLO looks for yolo11n.pt in the current folder. setup_flexo.sh downloads it here.
cd "$PKG"
exec ros2 launch hri_vision vision_pipeline.launch.py \
    camera_backend:=external \
    rgb_topic:=/rgb/image_raw \
    depth_topic:=/depth_to_rgb/image_raw
