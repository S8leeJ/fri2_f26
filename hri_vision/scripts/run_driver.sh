#!/usr/bin/env bash
# Start the Azure Kinect driver. Run scripts/setup_flexo.sh once first.
#
#   bash scripts/run_driver.sh
#
# Start this first and keep it running. Then start scripts/run_pipeline.sh
# in another terminal. Stop the pipeline first and this driver last.
#
# Run it at flexo's own screen. The Kinect depth engine needs the display.

KINECT_WS="${KINECT_WS:-/home/justin/bwi_ros2}"

[ -f "$KINECT_WS/install/setup.bash" ] || {
    echo "❌ FAILED: no driver build at $KINECT_WS. Run scripts/setup_flexo.sh to check the setup."
    exit 1
}

if pgrep -f azure_kinect_ros_driver > /dev/null; then
    echo "❌ FAILED: a Kinect driver already runs, and only one program can use the Kinect."
    echo "   Find it with: ps aux | grep -i azure_kinect | grep -v grep"
    echo "   If it is yours, stop it with: pkill -f azure_kinect_ros_driver"
    exit 1
fi

source /opt/ros/humble/setup.bash
source "$KINECT_WS/install/setup.bash"
export ROS_LOCALHOST_ONLY=1

# ros2 run, not ros2 launch: the driver launch file writes a URDF into the
# driver's workspace, and this account cannot write there.
# NFOV_UNBINNED sees to about 3.9 m. 16UC1 is depth in millimeters.
exec ros2 run azure_kinect_ros_driver node --ros-args \
    -p color_enabled:=true \
    -p depth_enabled:=true \
    -p color_resolution:=720P \
    -p fps:=15 \
    -p depth_mode:=NFOV_UNBINNED \
    -p depth_unit:=16UC1 \
    -p point_cloud:=false \
    -p rgb_point_cloud:=false
