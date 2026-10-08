# Read the Room

**Read the Room** is a UT Austin FRI research project on socially appropriate conversation initiation for a mobile robot (BWIbot). Instead of greeting everyone nearby, the robot fuses simple audio and vision cues into a structured JSON snapshot of the scene, then uses an LLM to decide whether speaking would be polite right now — remain silent, wait, or greet — before anything is said aloud.

The research question is whether that structured context is enough for an LLM to match human judgment about *when* to initiate, at latency that still works in real human–robot interaction. This repo also contains the FRI Autonomous Robots AprilTag-follower homework stack used as the navigation substrate.

| Piece | Where |
|---|---|
| Decision-layer design | [`docs/llm_decision_layer.md`](docs/llm_decision_layer.md) |
| Full build plan | [`conversation_initiator/IMPLEMENTATION_PLAN.md`](conversation_initiator/IMPLEMENTATION_PLAN.md) |
| Laptop MVP (no ROS) | [`conversation_initiator/mvp/`](conversation_initiator/mvp/) · [`MVP_PLAN.md`](conversation_initiator/MVP_PLAN.md) |

**Try the MVP** (Gemini or Anthropic, hand-written social vignettes):

```bash
cd conversation_initiator/mvp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add GEMINI_API_KEY and/or ANTHROPIC_API_KEY
python mvp.py --provider gemini
```

---

## FRI homework workspace setup

Use Ctr+Shift+V to paste in terminator.

```
# you shouldn't need to run this one (packages should already be installed)
sudo apt update && sudo apt install libgtk-3-dev libapriltag-dev
```
```
pip install --upgrade packaging --user
```
```
echo 'source /opt/ros/humble/setup.bash' >> ~/.bashrc
echo 'export COLCON_WS=~/bwi_ros2' >> ~/.bashrc 
mkdir bwi_ros2
cd bwi_ros2
mkdir src
```
```
cd ~/bwi_ros2
git clone https://github.com/UT-Austin-FRI-Autonomous-Robots/serial.git
```
```
cd ~/bwi_ros2/serial/
rm -rf build
mkdir build
cd build
cmake ..
make
```
```
cd ~/bwi_ros2/src
git clone --branch humble https://github.com/microsoft/Azure_Kinect_ROS_Driver.git
git clone https://github.com/Living-With-Robots-Lab/apriltag_ros.git
git clone https://github.com/utexas-bwi/bwi_ros2_common.git
git clone https://github.com/Living-With-Robots-Lab/segbot_description.git
git clone --recurse-submodules https://github.com/utexas-bwi/urg_node2.git
git clone https://github.com/Living-With-Robots-Lab/lidar.git
```

### On a V2
```
cd ~/bwi_ros2/src
git clone https://github.com/utexas-bwi/libsegwayrmp_ros2.git
mv libsegwayrmp_ros2/ libsegwayrmp
git clone https://github.com/utexas-bwi/segway_rmp_ros2.git
```

### Build
```
source ~/.bashrc
cd ~/bwi_ros2
source /opt/ros/humble/setup.bash
rosdep update
rosdep install --from-paths src -y --ignore-src
colcon build
source install/setup.bash
```
There will be warnings after you build for the first time, but hopefully no errors. Remember to run colcon build in your workspace root everytime you make a change.

---

## Run audio and vision on flexo

Use the robot flexo (IP `10.0.0.144`). Sit at its own screen, and log out every other account first.

### 1. Setup, once for each account

```bash
bash ~/fri2_f26/audio_signals_FRI_II/tools/setup_flexo.sh
```

```bash
bash ~/fri2_f26/hri_vision/scripts/setup_flexo.sh
```

Each script runs its checks in order and ends with `✅ Ready`, or stops with `❌ FAILED:` and the reason.
The installs stay in the account. Run a setup again after a `git pull` that changes a `requirements.txt`, or when a build or an import fails.

### 2. Run everything with one command

```bash
python3 ~/fri2_f26/fusion/fusion_publisher.py
```

It does these steps in order:

1. Loads ROS 2 and sets `ROS_LOCALHOST_ONLY=1`.
2. Starts the audio node (`audio_signals_FRI_II/tools/run_node.sh`). It rebuilds `audio_context`, opens the Kinect microphone, and publishes `/audio_context` once each second.
3. Starts the Kinect driver (`hri_vision/scripts/run_driver.sh`), and waits for `K4A Started`. The driver publishes the camera images.
4. Starts the vision pipeline (`hri_vision/scripts/run_pipeline.sh`). It rebuilds `hri_vision` and publishes `/hri/vision/context` several times each second.
5. Publishes the newest audio and vision messages together on `/social_context`, 10 times each second, with the age of each.

A program that already runs is used as it is. Each program writes its output to `fusion/logs/`.
Ctrl+C stops everything that the script started, with the driver last. Then log out.

To run the parts one at a time instead, run the three scripts from steps 2, 3, and 4 in separate terminals, in that order.
`audio_signals_FRI_II/RUN_ON_FLEXO.md` and `hri_vision/RUN_ON_FLEXO.md` explain each part and list fixes.

### 3. Check the topics

From any terminal on flexo:

```bash
ros2 daemon stop ; ros2 topic echo --once /audio_context --field data ; ros2 topic echo --once /hri/vision/context --field data
```

```bash
ros2 daemon stop ; ros2 topic echo /social_context --field data
```

The first command prints one audio message and one vision message. The second shows `/social_context` as it arrives.
A terminal needs ROS loaded and `ROS_LOCALHOST_ONLY=1`. The setup scripts add both to `~/.bashrc`.
