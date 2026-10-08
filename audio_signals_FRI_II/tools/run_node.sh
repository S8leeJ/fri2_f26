#!/usr/bin/env bash
# Build the audio node, then start it. Run tools/setup_flexo.sh once first.
#
#   bash tools/run_node.sh
#
# The build runs every time, so the node always uses the current code.
# It refuses to start when an audio node already runs, because two nodes would
# both publish /audio_context, and their messages would take turns.
#
# The node publishes /audio_context. To read it, run this in another terminal:
#
#   ros2 daemon stop ; ros2 topic echo /audio_context --field data

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if pgrep -f "audio_context[ /]node" > /dev/null; then
    echo "❌ FAILED: an audio node already runs. Two nodes would both publish /audio_context."
    echo "   Find it with: ps -eo user,pid,cmd | grep audio_context | grep -v grep"
    echo "   If it is yours, stop it with: pkill -INT -f \"audio_context[ /]node\""
    exit 1
fi

source /opt/ros/humble/setup.bash

colcon build --packages-select audio_context || {
    echo "❌ FAILED: the build did not finish. Run this, then try again: bash $ROOT/tools/setup_flexo.sh"
    exit 1
}
echo "✅ audio_context built"

source "$ROOT/install/setup.bash"
export ROS_LOCALHOST_ONLY=1

exec ros2 run audio_context node
