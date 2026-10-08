#!/usr/bin/env bash
# One-time setup for the audio node on flexo. Safe to run again.
#
#   bash tools/setup_flexo.sh
#
# Each step prints a check mark, or stops with FAILED and the reason.
# Then start the node with:
#
#   bash tools/run_node.sh
#
# RUN_ON_FLEXO.md explains each step.

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() { printf '\n== %s\n' "$1"; }
ok()   { printf '✅ %s\n' "$1"; }
fail() { printf '\n❌ FAILED: %s\n' "$1"; exit 1; }

step "1/8 Internet"
curl -sI --max-time 10 https://pypi.org > /dev/null \
    || fail "no internet. Connect flexo to Wi-Fi and run this again."
ok "internet"

step "2/8 ROS 2 Humble, loaded in every new terminal"
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

step "3/8 Python packages (this can take a few minutes)"
pip install --user -q -r requirements.txt "numpy<2"
ok "Python packages"

step "4/8 setuptools"
# A package in step 3 can pull in a newer setuptools, which breaks colcon build.
pip install --user -q setuptools==58.2.0
ok "setuptools 58.2.0"

step "5/8 Packages load, and the speech model is downloaded"
python3 -c "
import numpy, scipy, sounddevice, soundfile, faster_whisper
assert numpy.__version__.startswith('1.'), 'numpy ' + numpy.__version__ + ' must be below 2'
from audio_context.config import CONFIG as c
faster_whisper.WhisperModel(c['stt_model'], device=c['stt_device'], compute_type=c['stt_compute_type'])
" || fail "a package or the speech model does not load. For 'PortAudio library not found', ask the lab admin to install libportaudio2. Otherwise, check the internet."
ok "packages load, speech model ready"

step "6/8 Build the ROS package"
colcon build --packages-select audio_context
ok "audio_context built"

step "7/8 Microphone is connected"
python3 tools/check_devices.py \
    || fail "the microphone in config.py (input_device) is not connected. For the Kinect, check its power supply and USB cable."
ok "microphone found"

step "8/8 Microphone records"
# The output ends with one summary line. capture.py can print status lines before it.
MIC=$(python3 - <<'EOF'
import numpy as np
from audio_context.capture import AudioCapture
from audio_context.config import CONFIG

blocks = []
with AudioCapture(CONFIG) as cap:
    for block in cap.blocks():
        blocks.append(block.samples)
        if len(blocks) >= 12:   # about 1.5 seconds
            break
    name, channels, rate = cap.device_name, cap.channels, cap.source_rate

x = np.concatenate(blocks)
level = 20 * np.log10(np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-12)
assert level > -100, f"the microphone sends only silence ({level:.1f} dBFS)"
print(f"{name}, {channels} ch @ {rate} Hz, room level {level:.1f} dBFS")
EOF
) || fail "the microphone does not record. Stop any audio node that already runs. If it still fails, run: pactl set-card-profile \"\$(pactl list cards short | awk '/Kinect/ {print \$2}')\" off"
MIC=$(printf '%s\n' "$MIC" | tail -n 1)
ok "microphone records: $MIC"

printf '\n✅ Ready. All 8 checks passed.\n'
printf 'Open a new terminal, so that it reads ~/.bashrc. Then start the node:\n\n'
printf '  bash %s/tools/run_node.sh\n\n' "$ROOT"
