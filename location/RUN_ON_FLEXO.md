# Get the robot's location on flexo

This guide shows how to start the BWI navigation stack on flexo, set the robot's position in RViz, read the position from AMCL, and find the named room for that position.
It also shows how to run the `location-context` branch without any change to its code.

Tested on flexo on October 12, 2026.

## The pieces

| Piece | Where | What it does |
|---|---|---|
| Launch file | `/home/justin/bwi_ros2/src/bwi_ros2_common/bwi_launch/launch/segbot_v2.launch.py` | Starts the Segway base, the Hokuyo laser, the map, AMCL, and RViz. |
| Map | `.../nav2_bringup/maps/2/occ/ahg_full_closed.yaml` | AHG floor 2. 0.05 m for each pixel, origin (−75, −25), 1721 × 1106 pixels. |
| Room outlines | `.../nav2_bringup/maps/2/occ/locations.yaml` | 23 named locations (`l2_100` to `l2_elev_south`), as polygons in map pixels. |
| AMCL | started by the launch file | Finds the robot on the map. Publishes `/amcl_pose` (`geometry_msgs/PoseWithCovarianceStamped`). |
| RViz config | `/home/justin/bwi_ros2/install/bwi_launch/share/bwi_launch/config/rviz_config.rviz` | Opens with the launch file. |

`...` is `/home/justin/bwi_ros2/src/bwi_ros2_common`. The map numbers come from the GitHub copy of `bwi_ros2_common`.
Use `segbot_v2.launch.py`. `segbot_v4.launch.py` needs the package `segway`, which is not installed on flexo.

## Before you start

1. Sit at flexo's own screen and log in. RViz needs that screen, so SSH does not work for this.
2. Log out every other account on flexo. ROS programs in another account can stop yours from seeing each other.
3. Turn on the Segway base. AMCL needs laser data, and the laser may need power from the base.
4. Get the code, if your account does not have it yet:

   ```bash
   cd ~ && git clone https://github.com/S8leeJ/fri2_f26.git
   ```

5. Open Terminator. Every command below loads ROS itself, so it works in any new terminal.

## 1. Start navigation and RViz

```bash
source /home/justin/bwi_ros2/install/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 launch bwi_launch segbot_v2.launch.py
```

- Expected: RViz opens with the floor 2 map. The Navigation 2 panel shows `Navigation: active` and `Localization: active`.
- The terminal repeats `AMCL cannot publish a pose or update the transform. Please set the initial pose...`. This is normal until step 2.
- A red `RobotModel` entry in RViz is not a problem.

Keep this terminal running.

## 2. Set the robot's position in RViz

1. Find the robot's real spot on the map. Scroll to zoom.
2. Click **2D Pose Estimate** in the top toolbar.
3. Click the robot's spot, hold, and drag in the direction that the robot faces.

- Expected: the `cannot publish a pose` warnings stop, and the terminal shows `initialPoseReceived` and `Setting pose`.
- Click the real spot, not the robot icon. Before step 2, the icon is at the map's (0, 0).

## 3. Read the position

In a new terminal:

```bash
source /opt/ros/humble/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 daemon stop ; ros2 topic echo --once /amcl_pose --field pose.pose.position
```

- Expected: `x: ...  y: ...  z: 0.0`, in meters on the floor 2 map. On October 12, 2026, the robot read `x: -0.13  y: -0.40`.
- If the command waits and prints nothing, AMCL has no position or no laser data. Do step 2 again, then check the laser:

  ```bash
  source /opt/ros/humble/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 topic hz /scan
  ```

  You want about 10 Hz. If it prints nothing, turn on the base and wait about 10 seconds.

## 4. Find the room for a position

`locations.yaml` stores the rooms in map pixels. This converts them to meters and prints the room that contains the point. Put your `x` and `y` after `python3 -`:

```bash
python3 - -0.13 -0.40 <<'EOF'
import sys, yaml
M = "/home/justin/bwi_ros2/src/bwi_ros2_common/nav2_bringup/maps/2/occ/"
x, y = float(sys.argv[1]), float(sys.argv[2])
d = yaml.safe_load(open(M + "locations.yaml"))
H, RES, OX, OY = 1106, 0.05, -75.0, -25.0   # from ahg_full_closed.yaml and its .pgm
def inside(poly):
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit
rooms = [name for name, flat in zip(d["locations"], d["polygons"])
         if inside([(OX + flat[i] * RES, OY + (H - flat[i + 1]) * RES) for i in range(0, len(flat), 2)])]
print(rooms or "not inside any named location")
EOF
```

- Expected for the example: `['l2_202']`.
- The names are AHG room numbers. Someone must still decide which rooms count as a library, a hallway, or a lab.

## 5. Run the `location-context` branch

Do this in your own clone (see Before you start). The branch has no `package.xml`, so run the node with `python3`, not `ros2 run`.

```bash
cd ~/fri2_f26 && git fetch && git switch location-context
```

With steps 1 and 2 done, in a new terminal:

```bash
cd ~/fri2_f26 && source /opt/ros/humble/setup.bash && export ROS_LOCALHOST_ONLY=1 && python3 location_context_node.py
```

- Expected: one line for each pose, for example `Position (-0.13, -0.40) -> {'room_label': ..., 'room_type': ..., 'confidence': ...}`.
- The rooms in `location_context.py` are example rectangles between (0, 0) and (10, 8) m. Real positions on this map can fall outside them, so the node can print `unknown`. That is the code working. It needs real room coordinates.
- Rectangles do not fit this building well. If you draw a box around each room in `locations.yaml`, 33 pairs of boxes overlap, and the box of `l2_306` is inside the box of `l2_304`. The outlines in `locations.yaml` do not overlap, and step 4 tests a point against them.
- To go back to the main code: `git switch main`.

## Known limits

- AMCL publishes `/amcl_pose` only after it updates. When the robot does not move, a new pose can take a long time, and the node prints nothing. Set the pose again in RViz to send a new one.
- On October 12, 2026, the launch printed `Message Filter dropping message: frame 'nav_hokuyo_laser_link' ... earlier than all the data in the transform cache`. RViz and the costmaps dropped laser scans. AMCL then probably cannot correct the pose, so the pose stays where you clicked. For a robot at one fixed spot, this is enough.
- The launch file publishes `map → odom` and `odom → base_footprint` as fixed transforms (seen in the GitHub copy). So the pose may not follow the robot when it drives. Ask Justin if the robot must be tracked while it moves.
- The study schema has no location field yet (`conversation_initiator/SCHEMA.md` §8). The team must agree before a location goes into the LLM input.

## Problems

| You see | Do this |
|---|---|
| `ros2: command not found` | Use the full command, which starts with `source /opt/ros/humble/setup.bash`. |
| `Package 'bwi_launch' not found` | The first `source` in step 1 did not run. Run the whole step 1 command again. |
| `Package 'segway' not found` | You started `segbot_v4.launch.py`. Use `segbot_v2.launch.py`. |
| Segway or serial port errors | The base is off, or your account cannot open its port. AMCL and RViz still start. |
| RViz does not open | You are on SSH. Use flexo's own screen. |
| Step 3 shows nothing, and no warnings in step 1 | Every terminal needs `export ROS_LOCALHOST_ONLY=1`. Log out other accounts. |

## Stop

Press **Ctrl+C** in the node terminal, then in the launch terminal.
