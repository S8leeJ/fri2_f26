# Run Jev and the baseline on flexo

Both robots run from the `rule-baseline` branch. Run one robot at a time.

## 1. Once

```bash
cd ~/fri2_f26 && git switch rule-baseline && git pull && bash hri_vision/scripts/setup_flexo.sh
```

This also downloads MediaPipe's Face Landmarker model (about 4 MB), which the baseline needs.

## 2. Start the sensors

Terminal 1. Start it first and keep it running.

```bash
python3 ~/fri2_f26/fusion/fusion_publisher.py
```

## 3. Check the camera fields

Terminal 2:

```bash
bash ~/fri2_f26/hri_vision/scripts/view.sh json
```

Stand about 1.5 m in front of the camera:

| Do | Expect |
|---|---|
| Look at the camera | `head_angle_deg` and `body_angle_deg` near 0, `side_deg` near 0, `floor_distance_m` near 1.5 |
| Turn the head about 45° | `head_angle_deg` near 45 |
| Turn the whole body side on | `body_angle_deg` near 90 |
| Step to the edge of the view | `side_deg` near ±40 |

- `head_angle_deg` is always `null`: the Face Landmarker model did not load. Run step 1 again.
- `side_deg` is always `null`: the camera intrinsics (`/rgb/camera_info`) did not arrive.

Press Ctrl+C to stop `view.sh`.

## 4. Run one robot

Terminal 2.

Baseline:

```bash
cd ~/fri2_f26/conversation_initiator/mvp && python3 live_node.py --speak --provider baseline --turn-off
```

Check that it prints `baseline: Shi zones (cone 30 deg, body zone on) + ROS4HRI levels (window 2 s) + Hriscu rule ...`.

Jev:

```bash
cd ~/fri2_f26/conversation_initiator/mvp && python3 live_node.py --speak --provider jev --turn-off
```

Check that it prints `rules: off: scene only, the model decides, asked every 1 s`.

**To switch robots:** press Ctrl+C in Terminal 2, then start the other one. Keep Terminal 1 running.

**To stop:** press Ctrl+C in Terminal 2, then in Terminal 1.

## Recording the clips

- Use `--turn-off` for both robots, every time.
- Act out each scenario the same way for both robots.
- Each start adds a `run_start` line to `conversation_initiator/mvp/live_logs/<date>.jsonl`, with the robot's name (`provider`). Use it to match clips to runs.
- The logs hold what people said. Do not commit or share them.
