import numpy as np

from hri_vision.common import classify_direction, median_distance_mm, speed_mm_s


def test_direction():
    assert classify_direction(-150, 100) == "approaching"
    assert classify_direction(150, 100) == "receding"
    assert classify_direction(50, 100) == "stationary"


def walk(speed_mm_s_true, noise_mm, hz=10.0, seconds=1.0):
    rng = np.random.default_rng(0)
    n = int(hz * seconds) + 1
    return [(i / hz, 3000.0 + speed_mm_s_true * i / hz + rng.normal(0, noise_mm)) for i in range(n)]


def test_slow_walk_toward_the_robot_is_approaching():
    # 0.6 m/s at 10 frames a second is 60 mm a frame, which the old per-frame check missed.
    assert classify_direction(speed_mm_s(walk(-600, 40)), 250) == "approaching"
    assert classify_direction(speed_mm_s(walk(600, 40)), 250) == "receding"


def test_standing_with_depth_noise_is_stationary():
    assert classify_direction(speed_mm_s(walk(0, 40)), 250) == "stationary"


def test_speed_needs_enough_time():
    assert speed_mm_s([(0.0, 3000.0), (0.1, 2950.0)]) is None
    assert speed_mm_s([(0.0, 3000.0), (0.1, 2950.0), (0.2, 2900.0)]) is None


def test_median_depth():
    depth = np.full((100, 100), 2000, dtype=np.uint16)
    depth[0:10, :] = 0
    d = median_distance_mm(depth, [10, 10, 90, 90], 0.6, 250, 8000)
    assert d == 2000.0
