# Turn the robot toward the person

`turn_to_person.py` turns flexo in place so that the person it talks to is in the middle of the camera image.
When the conversation ends, it turns back to where it started.

Not run on the robot yet. Written October 12, 2026.
The rules were tested offline (`test_turner.py`). A turn test on flexo showed that `/odom` measures turns correctly, and that the base turns about twice as fast as commanded.

## What it does

- It turns only while `/engaged` is `true`, that is, after the robot greets or replies.
- It starts a turn only when the person is more than 12° off center for 1 second. It stops when the person is within 4°. Small movements do not turn the robot.
- It never turns more than 40° from the rest heading. The rest heading is the robot's heading at the first conversation of the run.
- When `/engaged` becomes `false`, it turns back to the rest heading.
- It turns in place only, at about 11° each second. It stops when the person is lost, when `/odom` stops, or when a turn takes longer than 6 seconds. Ctrl+C sends a stop.

## Before you start

- Ask Justin before the robot turns.
- Clear about 1 meter around the robot. Keep a hand near the emergency stop or the power switch.

## Run it

You need four terminals.

1. **Terminal 1: the base.** It gives `/cmd_vel` and `/odom`. `gui:=false` keeps RViz closed, to save CPU.

   ```bash
   source /home/justin/bwi_ros2/install/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 launch bwi_launch segbot_v2.launch.py gui:=false
   ```

2. **Terminal 2: the sensors.**

   ```bash
   python3 ~/fri2_f26/fusion/fusion_publisher.py
   ```

3. **Terminal 3: the decision node.**

   ```bash
   cd ~/fri2_f26/conversation_initiator/mvp && python3 live_node.py --speak --provider jev
   ```

4. **Terminal 4: a dry run first.** It prints what it would do and does not move the robot.

   ```bash
   python3 ~/fri2_f26/attention/turn_to_person.py --dry-run
   ```

   - Stand to the robot's right, about 1.5 m away, and let it greet you.
   - Expected: `turning right, person ... deg off center (dry run)`.
   - If it says `left` when you stand on the right, add `--flip` to every command below.
   - In a dry run the robot does not move, so you stay off center. `turn took too long, stopped` after 6 seconds is normal here.

5. **Terminal 4: the real run.** Press Ctrl+C to end the dry run, then:

   ```bash
   python3 ~/fri2_f26/attention/turn_to_person.py
   ```

   - Expected: after the greeting, it turns slowly until you are in the middle, then `centered, ... deg from the start`.
   - Walk away for more than 10 seconds. Expected: `conversation over, turning back ... deg`, then `back at the start heading`.

## Settings

| Option | Default | Meaning |
|---|---|---|
| `--speed` | 0.1 | Turn speed to command, in rad/s. The base turns about twice as fast. |
| `--deadband` | 12 | Degrees off center before a turn starts |
| `--hold` | 1.0 | Seconds off center before a turn starts |
| `--stop-within` | 4 | Degrees off center where a turn stops |
| `--max-turn` | 40 | Most degrees from the rest heading |
| `--flip` | off | Use it if the dry run names the wrong side |
| `--hfov`, `--image-width` | 90, 1280 | The Kinect color camera at 720P |

## Known limits

- `/cmd_vel` also has publishers from navigation (`behavior_server`, `velocity_smoother`). They were quiet on October 12, 2026. Do not give navigation a goal while this runs.
- The person's angle comes from the camera, with about 0.2 s of delay, so a turn can go a few degrees past the stop point.
- The person is the nearest person with a distance, as in `fusion_adapter.py`. Beyond about 4 m, depth is missing, and the robot does not turn.
- The audio node does not know that the robot moves. Motor noise during a turn can count as background sound.
