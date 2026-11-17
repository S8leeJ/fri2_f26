import math

import numpy as np

from hri_vision.common import median_distance_mm, motion_label, sideways_mm, speed_mm_s

HZ = 10.0
LIMITS = (250.0, 750.0, 400.0)  # the defaults in person_context_node.py


def track(start, velocity, seconds=1.0, noise_mm=40.0, hz=HZ):
    """(time_s, forward_mm, sideways_mm) for a straight walk, with depth and box noise."""
    rng = np.random.default_rng(0)
    (x, z), (vx, vz) = start, velocity
    return [(i / hz, z + vz * i / hz + rng.normal(0, noise_mm), x + vx * i / hz + rng.normal(0, noise_mm))
            for i in range(int(hz * seconds) + 1)]


def labels(samples, window_s=1.0):
    """The label after each new sample, as the node computes it."""
    out = []
    for i in range(len(samples)):
        recent = [s for s in samples[: i + 1] if samples[i][0] - s[0] <= window_s]
        out.append(motion_label(recent, *LIMITS))
    return out


def test_slow_walk_toward_the_robot_is_approaching():
    # 0.6 m/s at 10 frames a second is 60 mm a frame, which the old per-frame check missed.
    assert motion_label(track((0, 3000), (0, -600)), *LIMITS) == "approaching"
    assert motion_label(track((0, 3000), (0, 600)), *LIMITS) == "receding"


def test_standing_with_depth_noise_is_stationary():
    assert motion_label(track((0, 3000), (0, 0)), *LIMITS) == "stationary"


def test_walk_across_the_view_is_passing():
    # 2 m in front of the camera, left to right and right to left. The distance does not change.
    assert motion_label(track((-600, 2000), (1200, 0)), *LIMITS) == "passing"
    assert motion_label(track((600, 2000), (-1200, 0)), *LIMITS) == "passing"
    assert motion_label(track((-300, 2000), (600, 0)), *LIMITS) == "passing"


def test_walk_across_is_passing_for_the_whole_crossing():
    crossing = track((-1800, 2000), (1200, 0), seconds=3.0)
    assert set(labels(crossing)[4:]) == {"passing"}


def test_walk_down_a_hallway_past_the_robot_is_passing():
    # Toward the camera, but on a line 1.5 m to its side.
    assert motion_label(track((1500, 5000), (0, -1200)), *LIMITS) == "passing"


def test_walk_to_the_robot_from_the_side_is_approaching():
    # From 30 degrees off the axis, straight at the camera.
    x, z = 3000 * math.sin(math.radians(30)), 3000 * math.cos(math.radians(30))
    assert motion_label(track((x, z), (-x / 3, -z / 3)), *LIMITS) == "approaching"


def test_walk_away_at_an_angle_is_receding():
    # From 1 m in front of the camera, away and to the side.
    assert motion_label(track((0, 1000), (600, 900)), *LIMITS) == "receding"


def test_raised_arm_is_not_passing():
    # The box center moves 250 mm sideways in 0.5 s, then stays there.
    samples = [(i / HZ, 1500.0, 250.0 * min(1.0, max(0.0, (i / HZ - 0.5) / 0.5))) for i in range(31)]
    assert set(labels(samples)[4:]) == {"stationary"}


def test_new_track_is_unknown():
    assert motion_label(track((0, 3000), (0, -600))[:3], *LIMITS) == "unknown"


def test_no_image_width_falls_back_to_distance_only():
    on_axis = [(t, z, 0.0) for t, z, _ in track((0, 3000), (0, -600))]
    assert motion_label(on_axis, *LIMITS) == "approaching"


def test_sideways_from_the_box_center():
    # 90 degree view: the image edge is as far sideways as the depth.
    assert sideways_mm(2000, 640, 1280, 90) == 0
    assert math.isclose(sideways_mm(2000, 1280, 1280, 90), 2000)
    assert math.isclose(sideways_mm(2000, 0, 1280, 90), -2000)


def test_speed_needs_enough_time():
    assert speed_mm_s([(0.0, 3000.0), (0.1, 2950.0)]) is None
    assert speed_mm_s([(0.0, 3000.0), (0.1, 2950.0), (0.2, 2900.0)]) is None


def test_median_depth():
    depth = np.full((100, 100), 2000, dtype=np.uint16)
    depth[0:10, :] = 0
    d = median_distance_mm(depth, [10, 10, 90, 90], 0.6, 250, 8000)
    assert d == 2000.0
