#!/usr/bin/env bash
set -euo pipefail

echo "Image/depth-like topics:"
ros2 topic list -t | grep -Ei 'image|depth|rgb|color|camera' || true

echo
echo "Use:"
echo "  ros2 topic info <topic>"
echo "  ros2 topic hz <topic>"
echo "to verify candidate RGB/depth topics."
