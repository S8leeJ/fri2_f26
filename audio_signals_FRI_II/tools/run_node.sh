#!/usr/bin/env bash
# Start the audio node. Run tools/setup_flexo.sh once first.
#
#   bash tools/run_node.sh
#
# The node publishes /audio_context. To read it, run this in another terminal:
#
#   ros2 daemon stop ; ros2 topic echo /audio_context --field data

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[ -f "$ROOT/install/setup.bash" ] || {
    echo "No build found. Run this first: bash $ROOT/tools/setup_flexo.sh"
    exit 1
}

source /opt/ros/humble/setup.bash
source "$ROOT/install/setup.bash"
export ROS_LOCALHOST_ONLY=1

exec ros2 run audio_context node
