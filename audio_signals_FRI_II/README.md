
# Lab Machine Setup

    avenue.goat.report (if restarted, and asking for passcode)

    Username: mayankk
    Password: arrogance.underwire.rely

## New Setup — First Time Only

    git clone https://github.com/S8leeJ/fri2_f26.git (on terminal)
    cd fri2_f26/audio_signals_FRI_II (on terminal)
    code . (should open VSCode)

    git config --global user.email "mayank.konduri@gmail.com"
    git config --global user.name "MayankKonduri"

    source /opt/ros/humble/setup.bash

    pip install --user --upgrade pip
    pip install --user -r requirements.txt

    colcon build --packages-select audio_context
    source install/setup.bash

> **Note:** `libportaudio2` is already installed, so `sudo` is not required.

## New Terminal / Coming Back

    cd ~/fri2_f26/audio_signals_FRI_II
    git pull

### Free the USB microphone from PulseAudio

Only one program can open it. PulseAudio grabs it at login, so the node
silently falls back to the built-in mic. Symptom: `arecord -l` shows
`Subdevices: 0/1`. Needed on every machine, after every reboot.

    pactl list cards short
    pactl set-card-profile "$(pactl list cards short | grep -i camera | cut -f2)" off
    arecord -l                     # want Subdevices: 1/1
    python3 tools/check_devices.py
    python3 tools/check_levels.py

The card name changes across replugs, so look it up rather than hardcoding
it. Change `grep -i camera` if the mic is something else.

### Change Audio Enhancements
    Settings->Sound->Input->(Select the current camera-b4 microphone input)->Turn Audio Enhancements OFF!

    source /opt/ros/humble/setup.bash
    colcon build --packages-select audio_context
    source install/setup.bash

    ros2 run audio_context node

## Running Locally without ROS (for Testing)
    
    python main.py --show json --engaged

## Updating Code

After changing code:

    Ctrl+C

    colcon build --packages-select audio_context
    source install/setup.bash

    ros2 run audio_context node

## Second Terminal — View Output

Starting from:

    mayankkonduri@singularity-0:~$

Run:

> **Note:** Key idea is that you can subscribe anywhere as long as you do the /install/setup.bash from the folder that is publishing the topic.

    cd ~/fri2_f26
    source /opt/ros/humble/setup.bash
    source ~/fri2_f26/audio_signals_FRI_II/install/setup.bash
    ros2 topic echo /audio_context --field data