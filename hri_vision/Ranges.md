# Vision fields

The robot's camera, an Azure Kinect with color and depth, gives these fields several times each second.
Each field describes what the camera sees. No single field decides what the robot does. Each one is evidence to weigh with the other fields.
`null` or `"unknown"` means "not measured". It does not mean that nobody is there, or that a person faces away.

**`person_count`**: the number of people that the camera tracks now.
- People outside the camera's view are not counted. The view is about 90° from side to side.

**`people`**: one entry for each tracked person, with these fields.

**`id`**: a tracking number. It is not a stable identity.
- When a person is hidden for more than 2 seconds, or leaves and comes back, the same person can get a new `id`.

**`confidence`**: how sure the person detector is, from 0.35 to 1.
- Lower values are often a person who is partly hidden, at the edge of the view, or far away.

**`distance_m`**: the distance from the robot to the person, in meters.
- Measured from about 0.5 m to 3.9 m.
- `null` outside that range, near the edges of the view, or when `depth_fresh` is `false`.
- It is smoothed, so it is about 0.5 seconds late.

**`direction`**: `approaching`, `receding`, or `stationary`, along the line from the robot to the person.
- A person who walks across the view, at the same distance, is `stationary`.
- Slow walking can also read `stationary`.
- A new person starts as `stationary`.
- `unknown` when there is no distance.

**`dwell_time_s`**: the seconds since this `id` first appeared.
- It starts again at 0 when the person gets a new `id`.

**`orientation`**: which way the person's body and face point.
- `facing_robot`: a face is visible.
- `sideways`: the shoulders look narrow from the robot.
- `likely_facing_away`: the shoulders look wide, but no face is visible.
- `unknown`: not measured, for example in the first moment after a person appears.
- The face detector works up to about 2 m. Farther away, a person who faces the robot can read `likely_facing_away` or `unknown`.

**`face_visible`**: `true` when a face is visible, `false` when not. `null` when not measured.

**`gaze`**: `toward_robot` when a face is visible, otherwise `unknown`.
- It holds the same information as `face_visible`. It is not the direction of the eyes.

**`sensor_status`**: which measurements in this message are current.
- `depth_fresh: false`: `distance_m` and `direction` are not measured in this message.
- `orientation_fresh: false`: `orientation`, `gaze`, and `face_visible` are not measured in this message.

The message does not say where in the view a person is, for example left or right.
It has no field for whether people talk to each other.
