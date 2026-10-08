# Vision calibration notes

These notes are for people. `Ranges.md` is the short version for the LLM system prompt.
When a measurement here changes, update `Ranges.md` too.
`Ranges.md` only describes what values mean. It never tells the LLM what to do, because the LLM weighs the vision fields with the other fields.

## Camera settings

`scripts/run_driver.sh` starts the Azure Kinect with these settings:

| Setting | Value | Effect |
|---|---|---|
| `color_resolution` | `720P` | Color image of 1280 x 720. Field of view about 90° x 59°. |
| `depth_mode` | `NFOV_UNBINNED` | Depth from about 0.5 m to 3.86 m. Field of view about 75° x 65°, narrower than the color image. |
| `fps` | `15` | Camera frames each second. |
| `depth_unit` | `16UC1` | Depth in millimeters. The pipeline expects this unit. |

The depth view is narrower than the color view. So a person near the left or right edge of the image can have no depth, and `distance_m` is `null`.

## Pipeline settings

All are in `config/vision.yaml`.

| Node | Setting | Value | Effect |
|---|---|---|---|
| detection | `model` | `yolo11n.pt` | The smallest YOLO model, on the CPU. |
| detection | `confidence` | 0.35 | The lowest `confidence` that counts as a person. |
| detection | `max_rate_hz` | 12 | The highest detection rate. The real rate depends on the CPU. |
| person context | `center_crop_fraction` | 0.60 | Distance is the median depth of the middle 60% of the person's box. |
| person context | `distance_window` | 4 | `distance_m` is the mean of the last 4 readings, so it is about 0.5 seconds late. |
| person context | `direction_threshold_mm` | 100 | The smoothed distance must change by more than 100 mm between two updates to give `approaching` or `receding`. |
| person context | `track_grace_s` | 2.0 | An `id` that is gone for more than 2 seconds starts a new dwell time when it returns. |
| person context | `max_depth_age_s` | 0.25 | Depth older than this gives `depth_fresh: false`. |
| orientation | `max_rate_hz` | 5 | Orientation updates up to 5 times each second. |
| orientation | `sideways_shoulder_ratio` | 0.55 | Shoulder width divided by torso height. Below this value gives `sideways`. |
| orientation | face detector | `model_selection=0` | MediaPipe's short-range face model, for faces within about 2 m. |
| context builder | `orientation_max_age_s` | 1.0 | Orientation older than this gives `orientation_fresh: false`. |

## Observed on flexo

October 6, 2026, in the lab:

- `distance_m` from about 0.6 m to 2.25 m changed correctly as a person walked.
- `orientation` changed correctly between `facing_robot`, `likely_facing_away`, and `sideways` as a person turned.
- `approaching` and `receding` appeared when a person walked toward and away from the robot.
- `orientation` was `unknown` in the first message after a person appeared.

## Not measured yet

- How accurate `distance_m` is against a tape measure.
- The farthest distance at which `facing_robot` still works.
- The walking speed that `approaching` and `receding` need.
- The real detection rate on flexo.

## How to measure

Do these on flexo, at the place where the robot will stand. Run the driver and the pipeline, and watch `bash scripts/view.sh json`.

1. **Distance.** Stand still and face the robot at 1 m, 2 m, 3 m, and 4 m, measured with a tape. Write down `distance_m` at each mark.
2. **Facing range.** Face the robot at 1 m, 1.5 m, 2 m, 2.5 m, and 3 m. Write down the farthest distance that still gives `facing_robot`.
3. **Direction.** From 4 m, walk toward the robot at a normal speed, then slowly. Write down if `approaching` appears for each speed. Then walk across the view at 2 m, and check that it reads `stationary`.
4. **Detection rate.** Run `ros2 topic hz /hri/vision/detections`, and write down the average rate.

## Known limits

- `id` is not a stable identity. A person who is hidden, or leaves and comes back, can get a new `id`, and `dwell_time_s` starts again.
- `gaze` is a copy of `face_visible`. Nothing measures eye direction.
- `direction` measures only the change in distance. A person who walks across the view reads `stationary`. There is no `passing`.
- The final JSON drops the person's box, so it has no left or right position.
- Nothing measures whether people talk to each other.
- The orientation node uses the newest camera image with person boxes from a slightly older image. For a person who moves fast, the two can differ a little.

## Possible changes

These are options for the team. Nothing here is changed.

- MediaPipe's full-range face model (`model_selection=1`) works up to about 5 m. It could extend `facing_robot` beyond 2 m.
- The center of the person's box could give a left or right angle. Matched with the direction of a voice from the Kinect's microphones, it could tell who talks.
- A change in the box's left-right position could detect `passing`.
