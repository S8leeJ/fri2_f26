# HRI Vision Pipeline (ROS 2 Humble)

Ready-to-launch vision pipeline for the BWI/HRI robot project.

## What it outputs

`/hri/vision/context` (`std_msgs/String`) publishes compact JSON:

```json
{
  "person_count": 1,
  "people": [
    {
      "id": 3,
      "confidence": 0.91,
      "distance_m": 1.82,
      "direction": "approaching",
      "dwell_time_s": 6.4,
      "orientation": "facing_robot",
      "gaze": "toward_robot",
      "face_visible": true
    }
  ],
  "sensor_status": {
    "depth_fresh": true,
    "orientation_fresh": true
  }
}
```

Pipeline:

1. RGB image -> YOLO + ByteTrack -> person boxes + persistent IDs
2. Aligned depth + boxes -> distance, movement direction, dwell time
3. RGB + boxes -> MediaPipe Pose/Face Detection -> coarse orientation/gaze proxy
4. Context builder -> compact JSON for the LLM

## Important assumptions

- ROS 2 Humble
- RGB topic is a `sensor_msgs/msg/Image`
- Depth topic is a `sensor_msgs/msg/Image`
- Depth is already aligned to the RGB frame
- Depth encoding is `16UC1` in **millimeters**
- The robot may already have a Kinect/other RGB-D ROS driver. If it does, use `camera_backend:=external`.
- The orientation signal is deliberately coarse. `face_visible` is used as a proxy for "looking/facing toward robot"; this is not true eye-gaze estimation.

## 1. Put package in your workspace

```bash
mkdir -p ~/hri_ws/src
cp -r hri_vision ~/hri_ws/src/
cd ~/hri_ws
```

## 2. Install ROS dependencies

```bash
source /opt/ros/humble/setup.bash
rosdep install -i --from-path src --rosdistro humble -y
```

Install Python ML dependencies:

```bash
cd ~/hri_ws/src/hri_vision
bash scripts/install_python_deps.sh
```

If pip/ROS Python packages conflict, use a virtualenv that can see ROS packages:

```bash
python3 -m venv --system-site-packages ~/hri_venv
source ~/hri_venv/bin/activate
pip install -r ~/hri_ws/src/hri_vision/requirements.txt
```

## 3. Build

```bash
cd ~/hri_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select hri_vision
source install/setup.bash
```

## 4. Test BEFORE the robot (webcam)

The test mode publishes real webcam RGB and synthetic 2-meter depth. This verifies
YOLO, tracking, orientation, ROS topics, and JSON wiring. Distance will stay near
2.0 m by design.

```bash
ros2 launch hri_vision vision_pipeline.launch.py \
  camera_backend:=webcam \
  rgb_topic:=/hri/test/rgb \
  depth_topic:=/hri/test/depth
```

In another terminal:

```bash
source /opt/ros/humble/setup.bash
source ~/hri_ws/install/setup.bash
ros2 topic echo /hri/vision/context
```

## 5. On the robot: find the real camera topics

```bash
source /opt/ros/humble/setup.bash
bash ~/hri_ws/src/hri_vision/scripts/check_camera_topics.sh
```

You need:

- RGB/color image topic
- depth image **aligned to color**

Examples of names you might see:

```text
/camera/color/image_raw
/camera/aligned_depth_to_color/image_raw
```

Do not assume those exact names; inspect the robot.

Verify:

```bash
ros2 topic info /your/rgb/topic
ros2 topic info /your/aligned/depth/topic
ros2 topic hz /your/rgb/topic
ros2 topic hz /your/aligned/depth/topic
```

## 6. Launch on robot using its existing camera driver

```bash
ros2 launch hri_vision vision_pipeline.launch.py \
  camera_backend:=external \
  rgb_topic:=/YOUR/RGB/TOPIC \
  depth_topic:=/YOUR/ALIGNED/DEPTH/TOPIC
```

That is the normal final launch command.

## Optional: direct Azure Kinect capture with pyk4a

Only use this if the robot does NOT already expose usable ROS RGB/depth topics.

The native Azure Kinect Sensor SDK must be installed first. Then:

```bash
pip install pyk4a
```

Launch:

```bash
ros2 launch hri_vision vision_pipeline.launch.py \
  camera_backend:=pyk4a \
  rgb_topic:=/hri/kinect/rgb \
  depth_topic:=/hri/kinect/depth
```

## Main topics

| Topic | Type | Meaning |
|---|---|---|
| `/hri/vision/detections` | `std_msgs/String` | YOLO boxes + ByteTrack IDs |
| `/hri/vision/person_context` | `std_msgs/String` | Distance/direction/dwell |
| `/hri/vision/orientation` | `std_msgs/String` | Coarse orientation/gaze |
| `/hri/vision/context` | `std_msgs/String` | Final compact JSON |

## Tuning

Edit `config/vision.yaml`.

Useful parameters:

- `direction_threshold_mm`: increase if stationary people fluctuate between approaching/receding.
- `distance_window`: larger = smoother but slower response.
- `center_crop_fraction`: smaller values reduce background depth leaking into boxes.
- `max_rate_hz`: lower if CPU usage is high.
- `orientation_node.max_rate_hz`: MediaPipe is the second-heavyest stage; 3-5 Hz is usually enough for HRI context.
- `confidence`: YOLO person detection threshold.

## What is already implemented

- Person detection
- Person-only filtering
- Persistent ByteTrack IDs
- Per-person median aligned-depth distance
- Smoothed distance
- Approaching / stationary / receding
- Per-person dwell time
- Track grace handling
- Multi-person orientation crops
- Coarse facing/sideways/away signal
- Compact merged JSON
- One-command ROS 2 launch
- Webcam test mode
- Optional direct pyk4a camera mode

## What still must be verified on the actual robot

1. Exact RGB topic name
2. Exact aligned-depth topic name
3. Depth units/encoding (this package assumes `16UC1` millimeters)
4. CPU/GPU speed
5. Direction threshold for the real Kinect noise
6. Orientation threshold at the real hallway/library distances
7. Whether the existing robot stack expects a different final JSON field naming scheme

Those are deployment/calibration tasks, not missing core pipeline code.
