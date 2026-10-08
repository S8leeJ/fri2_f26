#!/usr/bin/env bash
# View the vision output. Start run_driver.sh and run_pipeline.sh first.
#
#   bash scripts/view.sh          the camera image with a box on each person
#   bash scripts/view.sh json     every JSON message on /hri/vision/context
#   bash scripts/view.sh camera   the plain camera image
#
# Stop it with Ctrl+C.

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1

case "${1:-boxes}" in
    boxes)
        exec python3 "$PKG/scripts/box_viewer.py"
        ;;
    json)
        # An old ROS helper process can have other settings and show nothing.
        ros2 daemon stop > /dev/null 2>&1
        exec ros2 topic echo /hri/vision/context --field data
        ;;
    camera)
        exec ros2 run rqt_image_view rqt_image_view /rgb/image_raw
        ;;
    *)
        echo "Use: bash $PKG/scripts/view.sh [boxes | json | camera]"
        exit 1
        ;;
esac
