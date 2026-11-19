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
FACE_LANDMARKER_URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

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

# The rule-based baseline needs MediaPipe's Face Landmarker model (about 4 MB).
MODEL=~/.cache/hri_vision/face_landmarker.task
if [ ! -f "$MODEL" ]; then
    mkdir -p "$(dirname "$MODEL")"
    curl -sfL -o "$MODEL" "$FACE_LANDMARKER_URL" \
        && echo "✅ Face Landmarker model downloaded" \
        || echo "⚠️  Face Landmarker model did not download: head_angle_deg stays empty"
fi

# YOLO looks for yolo11n.pt in the current folder. setup_flexo.sh downloads it here.
cd "$PKG"
exec ros2 launch hri_vision vision_pipeline.launch.py \
    camera_backend:=external \
    rgb_topic:=/rgb/image_raw \
    depth_topic:=/depth_to_rgb/image_raw \
    camera_info_topic:=/rgb/camera_info
