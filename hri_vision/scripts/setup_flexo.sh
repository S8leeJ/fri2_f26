#!/usr/bin/env bash
# One-time setup for the vision pipeline on flexo. Safe to run again.
#
#   bash scripts/setup_flexo.sh
#
# Each step prints a check mark, or stops with FAILED and the reason.
# Then start the pipeline in two terminals:
#
#   bash scripts/run_driver.sh      (first, and keep it running)
#   bash scripts/run_pipeline.sh
#
# The Kinect driver comes from an existing build. To use another build, set
# KINECT_WS, for example: KINECT_WS=~/bwi_ros2 bash scripts/setup_flexo.sh
#
# RUN_ON_FLEXO.md explains each step.

set -e

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(dirname "$PKG")"
KINECT_WS="${KINECT_WS:-/home/justin/bwi_ros2}"
DRIVER="$KINECT_WS/install/azure_kinect_ros_driver/lib/azure_kinect_ros_driver/node"

step() { printf '\n== %s\n' "$1"; }
ok()   { printf '✅ %s\n' "$1"; }
warn() { printf '⚠️  %s\n' "$1"; }
fail() { printf '\n❌ FAILED: %s\n' "$1"; exit 1; }

step "1/9 Internet"
curl -sI --max-time 10 https://pypi.org > /dev/null \
    || fail "no internet. Connect flexo to Wi-Fi and run this again."
ok "internet"

step "2/9 ROS 2 Humble, loaded in every new terminal"
[ -f /opt/ros/humble/setup.bash ] || fail "/opt/ros/humble/setup.bash does not exist."
# The ROS setup script is not written for set -e.
set +e
source /opt/ros/humble/setup.bash
set -e
# Every ROS terminal needs ROS loaded and the same ROS_LOCALHOST_ONLY value.
# Each line goes into ~/.bashrc only once.
for line in 'source /opt/ros/humble/setup.bash' 'export ROS_LOCALHOST_ONLY=1'; do
    grep -qxF "$line" ~/.bashrc || { echo "$line" >> ~/.bashrc; echo "added to ~/.bashrc: $line"; }
done
ok "ROS 2 Humble"

step "3/9 Python packages (this can take 5 to 15 minutes the first time)"
pip install --user -q -r "$PKG/requirements.txt"
ok "Python packages"

step "4/9 Build tools"
# An old packaging or a new setuptools breaks colcon build.
pip install --user -q --upgrade packaging
pip install --user -q setuptools==58.2.0
ok "packaging and setuptools 58.2.0"

step "5/9 Packages load, and the models are downloaded"
# run_pipeline.sh starts the pipeline in this folder, so YOLO finds its
# model file here and does not download it again.
cd "$PKG"
python3 -c "
import numpy, cv2, cv_bridge, matplotlib.pyplot, lap
import mediapipe as mp
from ultralytics import YOLO
assert numpy.__version__.startswith('1.'), 'numpy ' + numpy.__version__ + ' must be below 2'
assert hasattr(mp, 'solutions'), 'mediapipe ' + mp.__version__ + ' has no mp.solutions. Use 0.10.14.'
YOLO('yolo11n.pt')
mp.solutions.pose.Pose(model_complexity=0).close()
mp.solutions.face_detection.FaceDetection(model_selection=0).close()
print('numpy', numpy.__version__, '| cv2', cv2.__version__, '| mediapipe', mp.__version__)
" || fail "a package or a model does not load. Find the error above in Part D of RUN_ON_FLEXO.md."
ok "packages load, YOLO and MediaPipe models ready"

step "6/9 Build the ROS package"
cd "$REPO"
colcon build --symlink-install --packages-select hri_vision
ok "hri_vision built"

step "7/9 Kinect is connected"
usb=$(lsusb)
echo "$usb" | grep -q "Azure Kinect Depth Camera" && echo "$usb" | grep -q "Azure Kinect 4K Camera" \
    || fail "the Kinect cameras are not on USB. Check the Kinect power supply, and use a blue (USB 3) port."
ok "Kinect depth and color cameras found"

step "8/9 Kinect driver"
[ -x "$DRIVER" ] || fail "no driver build at $KINECT_WS. Set KINECT_WS to a working build, or ask the lab admin to install libk4a1.4-dev."
missing=$(ldd "$DRIVER" 2>&1 | grep -E "not found|Permission denied" || true)
[ -z "$missing" ] || fail "the driver build cannot run from this account: $missing"
ldd "$DRIVER" | grep -q "libk4a.so" || fail "the driver build does not find libk4a. The Kinect SDK runtime (libk4a1.4) is missing."
ok "driver build at $KINECT_WS works from this account"

step "9/9 Other sessions"
others=$(who | awk '{print $1}' | sort -u | grep -vx "$USER" || true)
if [ -n "$others" ]; then
    warn "other accounts are logged in: $(echo $others). Log them out. Their ROS programs can stop the pipeline from getting camera images."
else
    ok "no other account is logged in"
fi
if pgrep -f azure_kinect_ros_driver > /dev/null; then
    warn "a Kinect driver already runs. Only one program can use the Kinect. Stop it before run_driver.sh."
fi

printf '\n✅ Ready.\n'
printf 'Open two new terminals, so that they read ~/.bashrc. Then:\n\n'
printf '  bash %s/scripts/run_driver.sh      (first terminal, keep it running)\n' "$PKG"
printf '  bash %s/scripts/run_pipeline.sh    (second terminal)\n\n' "$PKG"
printf 'To view the output: bash %s/scripts/view.sh\n\n' "$PKG"
