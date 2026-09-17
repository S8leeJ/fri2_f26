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
