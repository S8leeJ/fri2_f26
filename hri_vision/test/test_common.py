import numpy as np

from hri_vision.common import classify_direction, median_distance_mm


def test_direction():
    assert classify_direction(-150, 100) == "approaching"
    assert classify_direction(150, 100) == "receding"
    assert classify_direction(50, 100) == "stationary"


def test_median_depth():
    depth = np.full((100, 100), 2000, dtype=np.uint16)
    depth[0:10, :] = 0
    d = median_distance_mm(depth, [10, 10, 90, 90], 0.6, 250, 8000)
    assert d == 2000.0
