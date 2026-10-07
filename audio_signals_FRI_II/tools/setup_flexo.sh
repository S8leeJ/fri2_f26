#!/usr/bin/env bash
# One-time setup for the audio node on flexo. Safe to run again.
#
#   bash tools/setup_flexo.sh
#
# Then start the node with:
#
#   bash tools/run_node.sh
#
# RUN_ON_FLEXO.md explains each step.

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() { printf '\n== %s\n' "$1"; }
fail() { printf '\nFAILED: %s\n' "$1"; exit 1; }

step "1/7 Internet"
curl -sI --max-time 10 https://pypi.org > /dev/null \
    || fail "no internet. Connect flexo to Wi-Fi and run this again."
echo "ok"

step "2/7 ROS 2 Humble"
[ -f /opt/ros/humble/setup.bash ] || fail "/opt/ros/humble/setup.bash does not exist."
# The ROS setup script is not written for set -e.
set +e
source /opt/ros/humble/setup.bash
set -e
echo "ok"

step "3/7 Python packages (this can take a few minutes)"
pip install --user -q -r requirements.txt "numpy<2"
# A package above can pull in a newer setuptools, which breaks colcon build.
pip install --user -q setuptools==58.2.0
echo "ok"

step "4/7 Check that the packages load"
python3 -c "
import numpy, scipy, sounddevice, soundfile, faster_whisper
assert numpy.__version__.startswith('1.'), 'numpy ' + numpy.__version__ + ' must be below 2'
print('ok, numpy', numpy.__version__)
" || fail "a package does not load. For 'PortAudio library not found', ask the lab admin to install libportaudio2."

step "5/7 Download the speech model"
python3 -c "
from audio_context.config import CONFIG as c
from faster_whisper import WhisperModel
WhisperModel(c['stt_model'], device=c['stt_device'], compute_type=c['stt_compute_type'])
print('ok,', c['stt_model'])
" || fail "the speech model did not load. Check the internet and run this again."

step "6/7 Build the ROS package"
colcon build --packages-select audio_context
echo "ok"

step "7/7 Microphone"
python3 tools/check_devices.py \
    || echo "WARNING: the microphone in config.py was not found, so the node uses the default microphone."

# Every ROS terminal needs ROS loaded and the same ROS_LOCALHOST_ONLY value.
# These lines make new terminals do both. Each line is added only once.
for line in 'source /opt/ros/humble/setup.bash' 'export ROS_LOCALHOST_ONLY=1'; do
    grep -qxF "$line" ~/.bashrc || { echo "$line" >> ~/.bashrc; echo "added to ~/.bashrc: $line"; }
done

printf '\nSetup complete.\n'
printf 'Open a new terminal, so that it reads ~/.bashrc. Then start the node:\n\n'
printf '  bash %s/tools/run_node.sh\n\n' "$ROOT"
