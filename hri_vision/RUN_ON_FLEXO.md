# Run the vision pipeline on flexo

Use the robot **flexo** (IP `10.0.0.144`).
It is the only robot with a working Azure Kinect driver build.
Other robots do not have one, so this guide does not work on them.

This guide starts from a new account and a fresh clone of `main`.
The first run takes about 30 minutes. Most of that time is the Python install.

Last tested: October 6, 2026.

## What you get

The pipeline publishes one JSON message for each processed camera frame on `/hri/vision/context` (`std_msgs/String`).
It also prints one of these messages each second in its terminal.
This is a real message from flexo:

```json
{"person_count":1,"people":[{"id":1,"confidence":0.92,"distance_m":1.826,"direction":"stationary","dwell_time_s":2.14,"orientation":"facing_robot","gaze":"toward_robot","face_visible":true}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
```

## Before you start

- Sit at flexo's own screen and log in with your lab account.
  Do not start the driver over SSH. The Kinect depth engine needs the display.
- Make sure that you are on flexo. The prompt ends in `@flexo:~$`, and this command shows `10.0.0.144`:

  ```bash
  hostname -I
  ```

- The Kinect has two cables. One goes to its power supply. The other goes into a blue (USB 3) port.
- Make sure that no other account is logged in on flexo.
  ROS programs that still run in another account's session can stop your pipeline from getting camera images.
  If another account is logged in, log it out first.
- Open one Terminator window and maximize it.

## Fast path: four scripts

If you only want the pipeline running, use the scripts in `hri_vision/scripts/`.
The rest of this guide explains each step, and Part D lists fixes.

1. Get the code, one time:

   ```bash
   cd ~ && git clone https://github.com/S8leeJ/fri2_f26.git
   ```

   If the folder already exists, run `cd ~/fri2_f26 && git switch main && git pull` instead.

2. Do the setup, one time. The script runs 9 checks in this order: internet, ROS (also added to `~/.bashrc`), Python packages, build tools, packages and models, build, Kinect connected, Kinect driver build, and other logged-in accounts.

   ```bash
   bash ~/fri2_f26/hri_vision/scripts/setup_flexo.sh
   ```

   - Expected: a ✅ line after each step, then `✅ Ready.`
   - A ⚠️ line is a warning. Read it, but the setup continues.
   - If the script stops with `❌ FAILED:`, read the message after it. Then find the problem in Part D.

3. Open a new terminal, and start the Kinect driver. Keep it running.

   ```bash
   bash ~/fri2_f26/hri_vision/scripts/run_driver.sh
   ```

   - Expected: `Found 1 sensors`, then `K4A Started`.

4. Open a second new terminal, and start the pipeline:

   ```bash
   bash ~/fri2_f26/hri_vision/scripts/run_pipeline.sh
   ```

   - Expected: `✅ hri_vision built`, `✅ Kinect driver found`, the four "ready" lines, and then one JSON line each second.
   - The script builds the package each time before it starts the pipeline.

5. Open a third new terminal, and view the output:

   ```bash
   bash ~/fri2_f26/hri_vision/scripts/view.sh
   ```

   - Without a word after it, `view.sh` shows the camera image with a green box on each person. Each label shows the ID, distance, direction, and orientation.
   - `view.sh json` shows every JSON message on `/hri/vision/context`.
   - `view.sh camera` shows the plain camera image.

6. To stop, press **Ctrl+C** in the viewer, then in the pipeline, then in the driver. Then log out.

The driver build is in `/home/justin/bwi_ros2`. To use another build, put `KINECT_WS=` and its path before the command, for example `KINECT_WS=~/bwi_ros2 bash ~/fri2_f26/hri_vision/scripts/run_driver.sh`.

## The four terminals

Split one Terminator window into four panes:

```
┌──────────────────────────┬──────────────────────────┐
│ 1 · GENERAL  (top-left)  │ 3 · DRIVER  (top-right)  │
│ setup and checks         │ starts the Kinect camera │
│                          │ keep it running          │
├──────────────────────────┼──────────────────────────┤
│ 2 · JSONS  (bottom-left) │ 4 · SUBSCRIBE            │
│ vision pipeline,         │     (bottom-right)       │
│ publishes the JSON       │ reads the JSON           │
│ keep it running          │ optional                 │
└──────────────────────────┴──────────────────────────┘
```

- Start order: 1 (setup), then 3 (driver), then 1 (checks), then 2 (pipeline), then 4 (subscriber).
- Stop order: 4, then 2, then 1, then 3. The driver always stops last.

| To do this | Press |
|---|---|
| Split the pane left and right | **Ctrl+Shift+E** |
| Split the pane top and bottom | **Ctrl+Shift+O** |
| Paste | **Ctrl+Shift+V** |
| Stop a running command | **Ctrl+C** |
| Close the pane | **Ctrl+Shift+W** |

Click a pane before you type in it. Commands go to the pane that you clicked last.
If a pasted command does not run, press **Enter**.

---

## Part A: One-time setup

Do Part A once for each account.
All of Part A happens in **Terminal 1 (GENERAL)**, which is the only pane at the start.
Wait for each command to finish before you start the next one.

### A1. Check the internet

```bash
curl -sI https://pypi.org | head -1
```

- Expected: `HTTP/2 200`
- If it prints nothing or hangs, connect flexo to Wi-Fi.

### A2. Check the Kinect

```bash
lsusb | grep -i microsoft
```

- Expected: about 5 lines, including `Azure Kinect Depth Camera` and `Azure Kinect 4K Camera`.
- If these lines are missing, reseat both cables. Try another blue port.

### A3. Check the driver build

The driver build is in Justin's workspace. Make sure that your account can use it:

```bash
ldd /home/justin/bwi_ros2/install/azure_kinect_ros_driver/lib/azure_kinect_ros_driver/node | grep -E "k4a|not found"
```

- Expected: `libk4a.so.1.4 => /lib/x86_64-linux-gnu/libk4a.so.1.4`, and no `not found`.
- If you see `Permission denied` or `No such file`, your account cannot use the build. Ask the lab admin.

Do not try to build the driver yourself.
The build needs `libk4a1.4-dev`, which is not installed, and you need `sudo` to install it.

### A4. Clone the repository

```bash
cd ~ && git clone https://github.com/S8leeJ/fri2_f26.git && cd ~/fri2_f26 && ls hri_vision
```

- Expected: the last line lists `README.md  RUN_ON_FLEXO.md  config  hri_vision  launch  ...`
- If the folder already exists, update it:

  ```bash
  cd ~/fri2_f26 && git switch main && git pull
  ```

### A5. Install the Python build tools

These two versions prevent two `colcon build` errors.

```bash
pip install --user --upgrade packaging && pip install --user setuptools==58.2.0
```

- Expected: the output ends with `Successfully installed setuptools-58.2.0`.
- Red "dependency conflicts" warnings are not a problem.

### A6. Install the Python packages

`requirements.txt` pins the versions that work on flexo. This step takes 5 to 15 minutes.

```bash
pip install --user -r ~/fri2_f26/hri_vision/requirements.txt
```

- Expected: the output ends with `Successfully installed ...`.
- Yellow "not on PATH" warnings and red "dependency conflicts" warnings are not a problem.
- Use `--user`. Do not use a virtualenv, because `ros2 run` and `ros2 launch` do not see its packages.

### A7. Check the packages

```bash
source /opt/ros/humble/setup.bash && python3 -c "import numpy, cv2, cv_bridge, matplotlib.pyplot, ultralytics, lap, mediapipe as mp; print('numpy', numpy.__version__, '| cv2', cv2.__version__, '| solutions', hasattr(mp, 'solutions'))"
```

- Expected: `numpy 1.26.4 | cv2 4.11.0 | solutions True`
- If you see an error, find it in Part D.

### A7.5. Set setuptools again

The A6 install can replace `setuptools` with a newer version.
The newer version breaks `colcon build --symlink-install`, so set it back:

```bash
pip install --user setuptools==58.2.0
```

- Expected: `Successfully installed setuptools-58.2.0`, or `Requirement already satisfied`.
- A red warning that a package "requires" a newer setuptools is not a problem.

### A8. Build the package

```bash
source /opt/ros/humble/setup.bash && cd ~/fri2_f26 && colcon build --symlink-install --packages-select hri_vision
```

- Expected: `Summary: 1 package finished`
- Yellow warnings are not a problem.

The setup is complete. Keep Terminal 1 open and go to Part B.

---

## Part B: Every run

### B1. Terminal 3 (DRIVER): start the Kinect

Click Terminal 1 and press **Ctrl+Shift+E**. The new pane on the right is Terminal 3.

```bash
source /opt/ros/humble/setup.bash && source /home/justin/bwi_ros2/install/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 run azure_kinect_ros_driver node --ros-args -p color_enabled:=true -p depth_enabled:=true -p color_resolution:=720P -p fps:=15 -p depth_mode:=NFOV_UNBINNED -p depth_unit:=16UC1 -p point_cloud:=false -p rgb_point_cloud:=false
```

- Expected: `Found 1 sensors`, then `STARTING CAMERAS`, then `K4A Started`. The command keeps running.
- Two yellow `WARN` lines about the "realtime offset" are normal.
- Paste the command. Do not type it. `720P` must have a capital `P`.

Keep Terminal 3 running. Do not type in it until you stop everything. Wait 5 seconds.

### B2. Terminal 1 (GENERAL): check the camera

Click Terminal 1. First, restart the ROS helper process and list the camera topics:

```bash
source /opt/ros/humble/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 daemon stop ; ros2 topic list | grep -E "rgb|depth"
```

- Expected: the list includes `/rgb/image_raw` and `/depth_to_rgb/image_raw`.

Check the frame rate:

```bash
ros2 topic hz /rgb/image_raw
```

- Expected: repeated lines of `average rate: 14.9...`
- Press **Ctrl+C** after 2 or 3 lines.

Check the depth format:

```bash
ros2 topic echo --once /depth_to_rgb/image_raw --field encoding
```

- Expected: `16UC1`

Optional: look at the camera image.

```bash
ros2 run rqt_image_view rqt_image_view
```

- Select `/rgb/image_raw` in the dropdown at the top left. You see live video.
- Close the window when you are done.

### B3. Terminal 2 (JSONS): start the pipeline

Click Terminal 1 and press **Ctrl+Shift+O**. The new pane at the bottom left is Terminal 2.

```bash
source /opt/ros/humble/setup.bash && source ~/fri2_f26/install/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 launch hri_vision vision_pipeline.launch.py camera_backend:=external rgb_topic:=/rgb/image_raw depth_topic:=/depth_to_rgb/image_raw
```

These lines must appear:

- 4 lines of `process started`
- `Context builder ready`
- `Person context ready`
- `Detection ready`
- `Orientation ready`
- Then one JSON line each second

These warnings are normal:

- `CUDA unknown error`. flexo has no NVIDIA GPU, so YOLO runs on the CPU.
- Lines that contain `absl`, `EGL`, `GL version`, or `XNNPACK`.
- `Feedback manager requires a model with a single signature inference`
- `SymbolDatabase.GetPrototype() is deprecated`

The first run downloads the YOLO and MediaPipe models. Later runs do not.
Keep Terminal 2 running.

### B4. Test the pipeline

Watch the JSON lines in Terminal 2.

| Do this | You see |
|---|---|
| Nobody is in view | `"person_count":0`, `"depth_fresh":true`, `"orientation_fresh":true` |
| Walk in | `"person_count":1` and a `"distance_m"` value in meters |
| Face the camera | `"orientation":"facing_robot"`, `"face_visible":true` |
| Turn your back | `"orientation":"likely_facing_away"` |
| Turn sideways | `"orientation":"sideways"` |
| Walk toward or away | `"direction":"approaching"` or `"receding"` |
| Stand still | `"direction":"stationary"`, and `"dwell_time_s"` increases |
| Leave | `"person_count":0` again |

### B5. Terminal 4 (SUBSCRIBE): read the JSON

Terminal 2 publishes the JSON on `/hri/vision/context`. Terminal 4 subscribes to it.
Terminal 2 prints only one message each second. Terminal 4 shows every message.

Click Terminal 3 and press **Ctrl+Shift+O**. The new pane at the bottom right is Terminal 4.
Do not type in Terminal 3 itself.

```bash
source /opt/ros/humble/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 daemon stop ; ros2 topic echo /hri/vision/context --field data
```

- Expected: JSON lines scroll fast, about one for each camera frame.
- Every part of this command is necessary. Without `ROS_LOCALHOST_ONLY=1`, or with an old ROS helper process, the pane shows nothing.

To subscribe from your own program, use the same topic name, the message type `std_msgs/String`, and `ROS_LOCALHOST_ONLY=1`.
This is a minimal Python subscriber:

```python
import json
import rclpy
from std_msgs.msg import String

rclpy.init()
node = rclpy.create_node("vision_reader")
node.create_subscription(
    String, "/hri/vision/context",
    lambda msg: print(json.loads(msg.data)["person_count"]), 10)
rclpy.spin(node)
```

---

## Part C: Stop everything

For each pane: click it, press **Ctrl+C**, wait for the prompt, and press **Ctrl+Shift+W**.

1. Terminal 4 (SUBSCRIBE)
2. Terminal 2 (JSONS)
3. Terminal 1 (GENERAL), if a command still runs there
4. Terminal 3 (DRIVER). Always stop the driver last, so that the Kinect closes correctly.

Then log out of flexo.
A driver that still runs in your session blocks the Kinect for every other account.
Other users cannot stop it without `sudo`.

---

## Part D: Problems and fixes

| You see | Do this |
|---|---|
| `canonicalize_version() got an unexpected keyword argument` | Do A5 again, then A8. |
| `option --editable not recognized` | Do A7.5, then A8. |
| `module 'mediapipe' has no attribute 'solutions'` | Run `pip install --user "mediapipe==0.10.14"`. |
| `_ARRAY_API not found` or `numpy.core.multiarray failed to import` | Run `pip install --user "numpy<2" "opencv-python==4.11.0.86" "opencv-contrib-python==4.11.0.86"`. |
| `package 'hri_vision' not found` | Do A8 again. |
| `setup_flexo.sh` says `the Kinect cameras are not on USB`, or `lsusb \| grep -i microsoft` shows fewer than 5 Kinect lines, or none | The Kinect is not fully connected. This happened on October 8, 2026, and this fix worked. Stop any Kinect driver first. Unplug both the power cable and the USB cable from the Kinect, and wait 15 seconds. Plug in the power cable first, and make sure that the light on the back comes on. Then plug the USB cable straight into a blue (USB 3) port on the laptop. Run `lsusb \| grep -i microsoft` again. You want 5 lines: `Azure Kinect Depth Camera`, `Azure Kinect 4K Camera`, `Microphone Array`, and two `USB Hub` lines. If the light stays off, check the power adapter. If the light is on but the lines do not come back, try another blue port or another USB cable. |
| Driver: `Permission denied` for `azure_kinect.urdf` | You used `ros2 launch`. Use the `ros2 run` command in B1. |
| Driver: `LIBUSB_ERROR_BUSY` or `Failed to open a K4A device` | Another program has the Kinect open. Run `ps aux \| grep -i azure_kinect \| grep -v grep`. If the line starts with your username, run `pkill -f azure_kinect_ros_driver`. If it starts with another username, log in to that account, stop its driver, and log out. If nothing shows, unplug the Kinect USB cable for 5 seconds. |
| Driver: `Invalid RGB Camera Resolution` or `Floating point exception` | The command has `720p`. Use `720P`, with a capital `P`. |
| Driver: an error about the `depth engine` | You are not at flexo's own screen. |
| Driver: `No such file` for `/home/justin/...` | The driver build moved. Ask the lab admin to install `libk4a1.4-dev`, so that you can build your own driver. |
| `topic ... does not appear to be published yet` | Run `ros2 daemon stop` and try again. Make sure that Terminal 3 still runs. |
| `"orientation":"unknown"` and `"orientation_fresh":false` in every line | The orientation node stopped. In Terminal 1, run `source ~/fri2_f26/install/setup.bash && ros2 run hri_vision orientation_node` to see the error. Then find the error in this table. |
| `"distance_m":null` | The person is more than about 3.9 m away, or the B2 encoding check did not show `16UC1`. |
| `"depth_fresh":false` | No depth images arrive. Do the B2 checks again. |
| All "ready" lines appear, but no JSON ever appears, and `ros2 topic hz /hri/vision/detections` says the topic is not published | Another account on flexo still runs ROS programs. This happened on October 6, 2026, and logging out the other account fixed it. Stop your panes, log out every other account, and start again from B1. |
| Terminal 4 shows nothing | Make sure that Terminal 2 still prints JSON. Then run the complete B5 command again, including `export ROS_LOCALHOST_ONLY=1` and `ros2 daemon stop`. |
| `requirements: Ultralytics requirement ['lap>=0.5.12'] not found, attempting AutoUpdate` | `lap` was not installed in A6. Ultralytics installs it by itself, and the pipeline still works. To avoid it, run `pip install --user "lap>=0.5.12"`. |

---

## Part E: Quick start

Use this after you complete Part A once.

1. Go to flexo's screen, log in, and open Terminator.
2. Terminal 3 (DRIVER): press **Ctrl+Shift+E** and run the B1 command. Wait for `K4A Started`.
3. Terminal 2 (JSONS): click the left pane, press **Ctrl+Shift+O**, and run the B3 command. Wait for `Orientation ready`.
4. Test with the B4 table.
5. Optional, Terminal 4 (SUBSCRIBE): click Terminal 3, press **Ctrl+Shift+O**, and run the B5 command.
6. Stop Terminal 4, then Terminal 2, then Terminal 3. Then log out.

To get the newest code before a run, update and rebuild in Terminal 1:

```bash
source /opt/ros/humble/setup.bash && cd ~/fri2_f26 && git pull && colcon build --symlink-install --packages-select hri_vision
```

---

## Notes

- **Why `ros2 run` for the driver.** The driver launch file writes a URDF file into the driver's workspace. Your account cannot write into Justin's workspace, so `ros2 launch` fails.
- **Why the camera topic arguments.** The launch defaults are RealSense topic names. The Azure Kinect driver publishes `/rgb/image_raw` and `/depth_to_rgb/image_raw`.
- **Why `NFOV_UNBINNED`.** It sees to about 3.9 m. The driver default, `WFOV_UNBINNED`, sees to about 2.2 m.
- **Why `ROS_LOCALHOST_ONLY=1`.** It keeps topics from other robots on the lab network out of your terminals. Set it in every terminal, or the terminals cannot see each other.
- **Why pinned versions.** ROS 2 Humble uses NumPy 1. Newer OpenCV needs NumPy 2. Newer MediaPipe removed `mp.solutions`, which the orientation node uses.
- **SSH.** From a computer on the lab network, `ssh YOUR_USERNAME@10.0.0.144` opens a terminal on flexo. You can do Part A over SSH. Start the driver (B1) at flexo's own screen. If SSH cannot connect, run `hostname -I` at flexo's screen, because the IP can change.
