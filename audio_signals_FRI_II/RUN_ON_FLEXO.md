# Run the audio node on flexo

Use the robot **flexo** (IP `10.0.0.144`).
This guide starts from a new account and a fresh clone of `main`.
The first run takes about 15 minutes. Most of that time is the Python install.

Last tested: October 6, 2026.

## What you get

The audio node listens to a microphone and publishes one JSON message each second on `/audio_context` (`std_msgs/String`).
It listens on two topics:

- `/engaged` (`std_msgs/Bool`): `true` turns transcription on.
- `/robot_speaking` (`std_msgs/Bool`): `true` makes the node ignore all audio, because the microphone only hears the robot.

This is a real message from the audio node (October 2, 2026):

```json
{"stamp": 1790974986.725697, "noise_floor_db": -42.0, "noise_level": "moderate", "speech_snr_db": 7.3, "speech_now": false, "speech_ratio_10s": 0.43, "seconds_since_speech": 1.4, "transcript": "Can you please let me know where to find the William Shakespeare books?", "tone": {"intensity_db": -36.3, "seconds": 5.7, "active_ratio": 0.98}, "engaged": true, "robot_speaking": false}
```

| Field | Meaning |
|---|---|
| `noise_floor_db` | Room level when nobody talks, in dBFS. More negative is quieter. `null` for the first 3 seconds. |
| `noise_level` | `quiet`, `moderate`, or `loud`. The cutoffs in `config.py` are not calibrated yet. |
| `speech_snr_db` | How far a voice rises above the room. Larger means closer or louder. |
| `speech_now` | Someone talks in this second. |
| `speech_ratio_10s` | Part of the last 10 seconds that had speech. Above 0.4 means a conversation. |
| `seconds_since_speech` | Length of the current pause. `0.0` while someone talks. |
| `transcript` | The last utterance as text. Empty unless `engaged` is `true`. |
| `speech_bearing_deg` | Direction of the voice in the last second, in degrees. 0 is straight ahead, negative is left. Only with the Kinect microphone array. Needs calibration, see `audio_context/CALIBRATION.md`. |
| `transcript_age_s` | Seconds since the person finished the sentence in `transcript`. `null` when there is no transcript. |
| `syntactically_complete` | `true` when `transcript` ends with `.`, `?`, or `!`. `false` when it has no end mark, or ends with `...`. `null` when there is no transcript. |
| `tone` | Level and length of the last utterance. |
| `engaged`, `robot_speaking` | The two flags, copied back from the input topics. |

`audio_context/Ranges.md` explains which values are normal. `audio_context/CALIBRATION.md` has the measurements behind them.

## Before you start

- Sit at flexo's screen and log in with your lab account.
- Make sure that no other account is logged in on flexo.
  ROS programs that still run in another account's session can stop your terminals from seeing each other.
- The node uses the microphone array in the Azure Kinect. `config.py` looks for a device name that contains `Azure Kinect`.
  The Kinect must have its power supply and its USB cable connected.
  To use the PlayStation Eye instead, set `input_device` in `config.py` to `"Camera-B4"`.
- Open one Terminator window and maximize it.

## Fast path: two scripts

If you only want the node running, use the two scripts in `tools/`.
The rest of this guide explains each step, and Part F lists fixes.

1. Get the code, one time:

   ```bash
   cd ~ && git clone https://github.com/S8leeJ/fri2_f26.git
   ```

   If the folder already exists, run `cd ~/fri2_f26 && git switch main && git pull` instead.

2. Do the setup, one time. The script runs 8 checks in this order: internet, ROS (also added to `~/.bashrc`), Python packages, setuptools, packages and speech model, build, microphone connected, and microphone records.

   ```bash
   bash ~/fri2_f26/audio_signals_FRI_II/tools/setup_flexo.sh
   ```

   - Expected: a ✅ line after each step, then `✅ Ready. All 8 checks passed.`
   - The step 8 line names the microphone, for example `Azure Kinect Microphone Array ..., 7 ch @ 48000 Hz, room level -59.0 dBFS`.
   - If the script stops with `❌ FAILED:`, read the message after it. Then find the problem in Part F.
   - Stop any running audio node before you run the script. Step 8 cannot record while the node holds the microphone.
   - You can run the script again at any time. It does not download again what is already installed.

3. Open a new terminal, and start the node:

   ```bash
   bash ~/fri2_f26/audio_signals_FRI_II/tools/run_node.sh
   ```

   - Expected: `✅ audio_context built`, then `publishing /audio_context every 1s`
   - The script builds the package each time before it starts the node, so the node always uses the current code.

4. Open a second new terminal, and read the JSON:

   ```bash
   ros2 daemon stop ; ros2 topic echo /audio_context --field data
   ```

5. Turn transcription on from a third terminal, and talk:

   ```bash
   ros2 topic pub -t 1 /engaged std_msgs/Bool "data: true"
   ```

New terminals already have ROS loaded and `ROS_LOCALHOST_ONLY=1`, because the setup script adds both to `~/.bashrc`.

## The three terminals

```
┌──────────────────────────┬──────────────────────────┐
│ 1 · GENERAL  (top-left)  │ 3 · SUBSCRIBE  (right)   │
│ setup, mic test, flags   │ reads /audio_context     │
├──────────────────────────┤ keep it running          │
│ 2 · AUDIO NODE           │                          │
│     (bottom-left)        │                          │
│ publishes /audio_context │                          │
│ keep it running          │                          │
└──────────────────────────┴──────────────────────────┘
```

- Start order: 1 (setup and mic test), then 2 (node), then 3 (subscriber), then 1 (flags).
- Stop order: 3, then 2.

| To do this | Press |
|---|---|
| Split the pane left and right | **Ctrl+Shift+E** |
| Split the pane top and bottom | **Ctrl+Shift+O** |
| Paste | **Ctrl+Shift+V** |
| Stop a running command | **Ctrl+C** |
| Close the pane | **Ctrl+Shift+W** |

Paste the commands. If you type them, watch for three common mistakes:

- Use `&&`. A single `&` runs the first command in the background, and the next command fails with `ros2: command not found`.
- Write `"data: true"` with a space after the colon.
- If a pasted line starts with `^[[200~`, press **Ctrl+C** and paste again.

---

## Part A: One-time setup

Do Part A once for each account. All of Part A happens in **Terminal 1 (GENERAL)**.

### A1. Check the internet

```bash
curl -sI https://pypi.org | head -1
```

- Expected: `HTTP/2 200`
- The first run downloads the speech model, so flexo must be online.

### A2. Get the code

```bash
cd ~ && git clone https://github.com/S8leeJ/fri2_f26.git && cd ~/fri2_f26/audio_signals_FRI_II && ls
```

- Expected: the list includes `RUN_ON_FLEXO.md  audio_context  main.py  package.xml  tools`.
- If the folder already exists, update it:

  ```bash
  cd ~/fri2_f26 && git switch main && git pull
  ```

### A3. Load ROS in every new terminal

Every ROS terminal needs ROS loaded and the same `ROS_LOCALHOST_ONLY` setting.
`ROS_LOCALHOST_ONLY=1` keeps flexo's ROS traffic off the lab network.
A terminal with this setting cannot see a terminal without it.
This step adds both to `~/.bashrc`, so that every new terminal has them:

```bash
echo 'source /opt/ros/humble/setup.bash' >> ~/.bashrc && echo 'export ROS_LOCALHOST_ONLY=1' >> ~/.bashrc
```

- Expected: no output.
- Close Terminal 1 and open a new Terminator window. Old terminals do not get the change.
- The commands in this guide still set both values. That does no harm.
- With this setting, other computers cannot see flexo's topics. To undo it, remove the two lines from `~/.bashrc`.

### A4. Install the Python packages

```bash
pip install --user -r ~/fri2_f26/audio_signals_FRI_II/requirements.txt "numpy<2"
```

- Expected: the output ends with `Successfully installed ...` or `Requirement already satisfied`.
- Red "dependency conflicts" warnings are not a problem.
- Use `--user`. Do not use a virtualenv, because `ros2 run` does not see its packages.

### A5. Set setuptools

A newer `setuptools` breaks `colcon build`, so set the version that ROS 2 Humble expects:

```bash
pip install --user setuptools==58.2.0
```

- Expected: `Successfully installed setuptools-58.2.0`, or `Requirement already satisfied`.

### A6. Check the packages

```bash
python3 -c "import sounddevice, soundfile, scipy, faster_whisper, numpy; print('ok', numpy.__version__)"
```

- Expected: `ok 1.26.4`
- If you see `PortAudio library not found`, flexo needs the system package `libportaudio2`. Ask the lab admin, because the install needs `sudo`.

### A7. Build the package

```bash
source /opt/ros/humble/setup.bash && cd ~/fri2_f26/audio_signals_FRI_II && colcon build --packages-select audio_context
```

- Expected: `Summary: 1 package finished`
- A yellow `Unknown distribution option: 'tests_require'` warning is not a problem.

---

## Part B: Test the microphone without ROS

Do this in **Terminal 1 (GENERAL)**.

### B1. Find the microphone

```bash
cd ~/fri2_f26/audio_signals_FRI_II && python3 tools/check_devices.py
```

- Expected: `FOUND`, with `Azure Kinect Microphone Array`, 7 channels, at 48000 Hz.
- If you see `NOT FOUND`, the node uses the default microphone, which may be the wrong one. Check the Kinect power supply and USB cable, or see Part F.
- To list every microphone, run `python3 tools/check_devices.py --list`.

### B2. Run a 30-second test

```bash
python3 main.py --show json --engaged --seconds 30
```

Expected:

- After about 3 seconds, one JSON line each second.
- `noise_floor_db` changes from `null` to a number.
- Talk for a few seconds. `speech_now` becomes `true`, and `speech_snr_db` shows a number.
- About 1 to 2 seconds after you stop, `transcript` shows your words.
- Press **Enter**. `robot_speaking` becomes `true`, and the measurements become `null`. Press **Enter** again to switch back.
- After 30 seconds, the program stops and prints a summary.

The first run downloads the speech model (about 75 MB). Later runs do not.

---

## Part C: Every run

### C1. Terminal 2 (AUDIO NODE): start the node

Click Terminal 1 and press **Ctrl+Shift+O**. The new pane at the bottom left is Terminal 2.

```bash
source /opt/ros/humble/setup.bash && source ~/fri2_f26/audio_signals_FRI_II/install/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 run audio_context node
```

- Expected: `publishing /audio_context every 1s`. The command keeps running.
- An occasional `audio status: input overflow` line is not a problem.

Keep Terminal 2 running.

### C2. Terminal 3 (SUBSCRIBE): read the JSON

Click Terminal 1 and press **Ctrl+Shift+E**. The new pane on the right is Terminal 3.

```bash
source /opt/ros/humble/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 daemon stop ; ros2 topic echo /audio_context --field data
```

- Expected: one JSON line each second, with `"engaged": false` and `"transcript": ""`.
- `ros2 daemon stop` restarts the ROS helper process. An old helper process can have the wrong setting, and then the pane shows nothing.

Keep Terminal 3 running.

### C3. Terminal 1 (GENERAL): set the flags

Turn transcription on:

```bash
source /opt/ros/humble/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 topic pub -t 3 /engaged std_msgs/Bool "data: true"
```

- Expected: `publishing #1 ... data=True` three times. Then the command stops.
- Terminal 2 logs `engaged = True`.

Tell the node that the robot talks, and then that it stopped:

```bash
ros2 topic pub -t 3 /robot_speaking std_msgs/Bool "data: true"
```

```bash
ros2 topic pub -t 3 /robot_speaking std_msgs/Bool "data: false"
```

Turn transcription off:

```bash
ros2 topic pub -t 3 /engaged std_msgs/Bool "data: false"
```

The node keeps the last value that it received.
When a publisher stops, the flag does not go back to `false`. Send `"data: false"` to change it.

### C4. Test the node

Watch the JSON lines in Terminal 3.

| Do this | You see |
|---|---|
| Stay quiet | `"speech_now": false`, and `"seconds_since_speech"` increases |
| Talk for a few seconds | `"speech_now": true`, a number in `"speech_snr_db"`, and `"seconds_since_speech": 0.0` |
| Talk with `engaged` true | `"transcript"` shows your words 1 to 2 seconds after you stop |
| Talk with `engaged` false | `"transcript": ""` |
| Send `robot_speaking` true | All measurements become `null` |
| Send `robot_speaking` false | The numbers come back after about 0.5 seconds |
| Send `engaged` false | `"transcript"` becomes `""` |

---

## Part D: Stop everything

For each pane: click it, press **Ctrl+C**, wait for the prompt, and press **Ctrl+Shift+W**.

1. Terminal 3 (SUBSCRIBE)
2. Terminal 2 (AUDIO NODE). A red `rcl_shutdown already called` traceback can appear. It is not a problem.

Then log out of flexo.

---

## Part E: Update the code

In Terminal 1, get the newest code and build again:

```bash
source /opt/ros/humble/setup.bash && cd ~/fri2_f26 && git pull && cd audio_signals_FRI_II && colcon build --packages-select audio_context
```

Then stop the node in Terminal 2 and start it again with the C1 command.
Do this after every change to the code, because this build copies the code into `install/`.
`tools/run_node.sh` does this build for you each time it starts the node.

---

## Part F: Problems and fixes

| You see | Do this |
|---|---|
| `ros2: command not found` | ROS is not loaded in this terminal. Run `source /opt/ros/humble/setup.bash`. Check that the command uses `&&`, not `&`. |
| `The passed value needs to be a dictionary in YAML format` | Write `"data: true"` with a space after the colon. |
| `topic [/audio_context] does not appear to be published yet` | Make sure that Terminal 2 still runs. Then run the complete C2 command again. Every terminal needs `export ROS_LOCALHOST_ONLY=1`. |
| `No executable found` | The command has a typo, or the build did not run. Do A7 again, then run the C1 command. |
| `option --editable not recognized` or `canonicalize_version() got an unexpected keyword argument` | Run `pip install --user --upgrade packaging`, then do A5 and A7 again. |
| `PortAudio library not found` | Ask the lab admin to install `libportaudio2`. |
| `check_devices.py` shows `NOT FOUND` | Check the Kinect power supply and USB cable. Wait 5 seconds and run B1 again. |
| `check_levels.py` says `Very low. Raise the capture volume` | The Kinect records quietly, with speech peaks near -30 dBFS. Transcription still works. To raise the level, run `alsamixer -c 2`, press F4, and raise the capture control. |
| `"speech_now"` never becomes `true` when you talk | The node listens to the wrong microphone, or the input volume is low. Run B1. Check the input volume in Settings, Sound, Input. |
| The microphone shows in `arecord -l` with `Subdevices: 0/1`, or capture fails with `Device unavailable` | Another program holds the microphone. Stop any audio node that runs. If that does not help, PulseAudio holds it. Run `pactl set-card-profile "$(pactl list cards short \| awk '/Kinect/ {print $2}')" off`. For the PlayStation Eye, use `/Camera-B4/` in place of `/Kinect/`. Then run `arecord -l` again. You want `Subdevices: 1/1`. Do this again after each reboot. |
| `transcription unavailable, carrying on without it` | The speech model did not download. Check the internet (A1), then start the node again. |
| `"transcript"` stays `""` | Make sure that `"engaged"` is `true` and that `"speech_now"` becomes `true` when you talk. |
| `"noise_floor_db": null` | Normal for the first 3 seconds, and after the robot talks for more than 10 seconds. |
| A red `build failed` line in Terminal 2 | A known bug. One JSON message is lost. The node continues. |

---

## Part G: Quick start

Use this after you complete Part A once.

1. Go to flexo's screen, log in, and open Terminator. Make sure that the Kinect has power.
2. Terminal 2 (AUDIO NODE): press **Ctrl+Shift+O** and run the C1 command. Wait for `publishing /audio_context every 1s`.
3. Terminal 3 (SUBSCRIBE): click the top-left pane, press **Ctrl+Shift+E**, and run the C2 command.
4. Terminal 1 (GENERAL): set the flags with the C3 commands, and test with the C4 table.
5. Stop Terminal 3, then Terminal 2. Then log out.

---

## Notes

- **Privacy.** Raw audio stays in memory. The node writes only levels and timestamps to `data/background.db` and `data/voice.db`, in the folder where you start it. Transcription runs only while `engaged` is `true`.
- **Vision at the same time.** The audio node and the vision pipeline (`hri_vision/RUN_ON_FLEXO.md`) can run at the same time in separate panes. They use different devices.
- **Calibration.** `noise_floor_db` is relative to the microphone, so its value changes with the microphone and its volume. The `noise_level` cutoffs in `config.py` are placeholders until someone measures the room at the study spot.
