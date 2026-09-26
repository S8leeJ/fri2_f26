# Lab Machine Setup

## New Setup — First Time Only

    git clone https://github.com/S8leeJ/fri2_f26.git
    cd fri2_f26/audio_signals_FRI_II

    source /opt/ros/humble/setup.bash

    pip install --user --upgrade pip
    pip install --user -r requirements.txt

    colcon build --packages-select audio_context
    source install/setup.bash

> **Note:** `libportaudio2` is already installed, so `sudo` is not required.

## New Terminal / Coming Back

    cd ~/fri2_f26/audio_signals_FRI_II
    git pull

    source /opt/ros/humble/setup.bash
    colcon build --packages-select audio_context
    source install/setup.bash

    ros2 run audio_context node

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

    cd ~/fri2_f26
    source /opt/ros/humble/setup.bash
    source ~/fri2_f26/audio_signals_FRI_II/install/setup.bash
    ros2 topic echo /audio_context