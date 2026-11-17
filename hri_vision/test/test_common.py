import math

import numpy as np

from hri_vision.common import (
    classify_direction,
    head_turn,
    image_x,
    median_distance_mm,
    merge_orientation,
    speed_mm_s,
)


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


def face(nose_x=0.0, nose_drop=20.0, roll_deg=0.0):
    """Right eye, left eye, nose, mouth: eyes 60 px apart, mouth 40 px below them."""
    a = math.radians(roll_deg)
    points = [(-30.0, 0.0), (30.0, 0.0), (nose_x, nose_drop), (0.0, 40.0)]
    return [(200 + x * math.cos(a) - y * math.sin(a), 150 + x * math.sin(a) + y * math.cos(a))
            for x, y in points]


def test_head_turn_of_a_face_toward_the_camera():
    yaw, pitch = head_turn(*face())
    assert math.isclose(yaw, 0.0, abs_tol=1e-9) and math.isclose(pitch, 0.5)


def test_head_turn_to_the_side_and_down():
    for nose_x in (20.0, -20.0):
        assert math.isclose(head_turn(*face(nose_x=nose_x))[0], 1 / 3)
    assert math.isclose(head_turn(*face(nose_drop=32.0))[1], 0.8)


def test_head_tilted_to_one_side_gives_the_same_values():
    for roll in (-25.0, 25.0):
        assert all(math.isclose(a, b, abs_tol=1e-9)
                   for a, b in zip(head_turn(*face(roll_deg=roll)), head_turn(*face())))


def test_points_that_are_not_a_face_give_none():
    assert head_turn((10.0, 10.0), (10.0, 10.0), (10.0, 20.0), (10.0, 30.0)) is None


def test_image_x_runs_from_the_left_edge_to_the_right_edge():
    assert image_x((0, 0, 0, 10), 1280) == -1.0
    assert image_x((600, 0, 680, 10), 1280) == 0.0
    assert image_x((1280, 0, 1280, 10), 1280) == 1.0
    assert image_x((800, 0, 960, 10), 1280) == 0.375


def test_image_x_is_none_without_an_image_width():
    assert image_x((600, 0, 680, 10), None) is None
    assert image_x((600, 0, 680, 10), 0) is None


def test_merge_keeps_the_head_angles_and_drops_the_box():
    person = {"id": 3, "bbox": [1, 2, 3, 4], "distance_m": 1.5, "image_x": 0.2}
    orientation = {"id": 3, "orientation": "facing_robot", "gaze": "toward_robot", "face_visible": True,
                   "head_yaw": 0.31, "head_pitch": 0.5, "shoulder_ratio": 0.9}
    assert merge_orientation(person, orientation) == {
        "id": 3, "distance_m": 1.5, "image_x": 0.2, "orientation": "facing_robot", "gaze": "toward_robot",
        "face_visible": True, "head_yaw": 0.31, "head_pitch": 0.5}


def test_merge_without_orientation_is_unknown():
    merged = merge_orientation({"id": 3, "bbox": [1, 2, 3, 4]}, None)
    assert merged == {"id": 3, "orientation": "unknown", "gaze": "unknown", "face_visible": None,
                      "head_yaw": None, "head_pitch": None}
