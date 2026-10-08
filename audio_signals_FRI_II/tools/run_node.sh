#!/usr/bin/env bash
# Build the audio node, then start it. Run tools/setup_flexo.sh once first.
#
#   bash tools/run_node.sh
#
# The build runs every time, so the node always uses the current code.
#
# The node publishes /audio_context. To read it, run this in another terminal:
#
#   ros2 daemon stop ; ros2 topic echo /audio_context --field data

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source /opt/ros/humble/setup.bash

colcon build --packages-select audio_context || {
    echo "❌ FAILED: the build did not finish. Run this, then try again: bash $ROOT/tools/setup_flexo.sh"
    exit 1
}
echo "✅ audio_context built"

source "$ROOT/install/setup.bash"
export ROS_LOCALHOST_ONLY=1

exec ros2 run audio_context node
