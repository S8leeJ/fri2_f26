# Turn the robot toward the person

`turn_to_person.py` turns flexo in place so that the person it talks to is in the middle of the camera image.
When the conversation ends, it turns back to where it started.

Not run on the robot yet. Written October 12, 2026.
The rules were tested offline (`test_turner.py`). A turn test on flexo showed that `/odom` measures turns correctly, and that the base turns about twice as fast as commanded.

## What it does

- It turns only while `/engaged` is `true`, that is, after the robot greets or replies.
- It starts a turn only when the person is more than 8° off center for 0.3 seconds. It stops when the person is within 3°. Small movements do not turn the robot.
- It turns faster when the person is far off center and slower near the center, so the turn is smooth. It corrects for the age of the camera image (about 0.2 s), from the `/odom` headings since the image was taken.
- It never turns more than 40° from the rest heading. The rest heading is the robot's heading at the first conversation of the run.
- When `/engaged` becomes `false`, it turns back to the rest heading.
- It turns in place only, at up to about 29° each second. It stops when the person is lost, when `/odom` stops, or when a turn takes longer than 6 seconds. Ctrl+C sends a stop.

## Before you start

- Ask Justin before the robot turns.
- Clear about 1 meter around the robot. Keep a hand near the emergency stop or the power switch.

## Run it

`live_node.py --speak` starts the turner by itself. It needs no terminal of its own.
It moves only when the BWI base runs, because it needs `/odom` to measure turns.

1. **Terminal 1: the base.** It gives `/cmd_vel` and `/odom`. `gui:=false` keeps RViz closed, to save CPU.

   ```bash
   source /home/justin/bwi_ros2/install/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 launch bwi_launch segbot_v2.launch.py gui:=false
   ```

2. **Terminal 2: the sensors.**

   ```bash
   python3 ~/fri2_f26/fusion/fusion_publisher.py
   ```

3. **Terminal 3: the decision node, with a dry run of the turner first.** It prints the turns and does not move the robot.

   ```bash
   cd ~/fri2_f26/conversation_initiator/mvp && python3 live_node.py --speak --provider jev --turn-dry-run
   ```

   - Expected at start: `turning: dry run, prints only`.
   - Stand to the robot's right, about 1.5 m away, and let it greet you.
   - Expected: `turn: turning right, person ... deg off center (dry run)`.
   - If it says `left` when you stand on the right, stop and tell the team: the image is mirrored, and the turner needs `--flip`.
   - In a dry run the robot does not move, so you stay off center. `turn took too long, stopped` after 6 seconds is normal here.

4. **Terminal 3: the real run.** Press Ctrl+C, then start it without `--turn-dry-run`:

   ```bash
   python3 live_node.py --speak --provider jev
   ```

   - Expected at start: `turning: on, moves only when the base sends /odom`.
   - After the greeting, it turns slowly until you are in the middle, then `turn: centered, ... deg from the start`.
   - Walk away for more than 5 seconds. Expected: `turn: conversation over, turning back ... deg`, then `turn: back at the start heading`.

## Turn it off or remove it

- Turning is on with `--speak`. The only switch that turns it off is `--turn-off`: `python3 live_node.py --speak --provider jev --turn-off`.
- Without the base (Terminal 1), there is no `/odom`, so the robot never turns.
- To remove it for good, delete the `attention/` folder. `live_node.py` then prints `turning: off, attention/turn_to_person.py not found` and works as before.
- The turner can also run alone, for tests: `python3 ~/fri2_f26/attention/turn_to_person.py --dry-run`.

## Settings

These are options of `turn_to_person.py` when it runs alone. `live_node.py` uses the defaults.

| Option | Default | Meaning |
|---|---|---|
| `--speed` | 0.25 | Fastest turn speed to command, in rad/s. The base turns about twice as fast. |
| `--deadband` | 8 | Degrees off center before a turn starts |
| `--hold` | 0.3 | Seconds off center before a turn starts |
| `--stop-within` | 3 | Degrees off center where a turn stops |
| `--max-turn` | 40 | Most degrees from the rest heading |
| `--flip` | off | Use it if the dry run names the wrong side. Only when the turner runs alone. |
| `--hfov`, `--image-width` | 90, 1280 | The Kinect color camera at 720P |

## Known limits

- `/cmd_vel` also has publishers from navigation (`behavior_server`, `velocity_smoother`). They were quiet on October 12, 2026. Do not give navigation a goal while this runs.
- The camera image is about 0.2 s old. The turner corrects for the robot's own turn since then, but not for the person's own movement.
- The person is the nearest person with a distance, as in `fusion_adapter.py`. Beyond about 4 m, depth is missing, and the robot does not turn.
- The audio node does not know that the robot moves. Motor noise during a turn can count as background sound.
