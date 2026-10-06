import json
from typing import Any, Dict, Optional

import numpy as np


def ros_time_to_float(stamp) -> float:
    return float(stamp.sec) + float(stamp.nanosec) / 1_000_000_000.0


def now_float(node) -> float:
    return node.get_clock().now().nanoseconds / 1_000_000_000.0


def safe_json_loads(data: str) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(data)
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def clamp_box(box, width: int, height: int):
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    x1 = max(0, min(width - 1, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height - 1, y1))
    y2 = max(0, min(height, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def central_crop_box(box, fraction: float):
    x1, y1, x2, y2 = box
    fraction = max(0.1, min(1.0, float(fraction)))
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    half_w = (x2 - x1) * fraction / 2.0
    half_h = (y2 - y1) * fraction / 2.0
    return (
        int(round(cx - half_w)),
        int(round(cy - half_h)),
        int(round(cx + half_w)),
        int(round(cy + half_h)),
    )


def median_distance_mm(depth_image: np.ndarray, box, center_fraction: float, min_mm: int, max_mm: int):
    h, w = depth_image.shape[:2]
    box = clamp_box(box, w, h)
    if box is None:
        return None

    crop_box = central_crop_box(box, center_fraction)
    crop_box = clamp_box(crop_box, w, h)
    if crop_box is None:
        return None

    x1, y1, x2, y2 = crop_box
    crop = depth_image[y1:y2, x1:x2]

    if crop.size == 0:
        return None

    # Azure Kinect aligned depth is normally uint16 millimeters.
    valid = crop[(crop >= min_mm) & (crop <= max_mm)]
    if valid.size == 0:
        return None

    return float(np.median(valid))


def classify_direction(delta_mm: float, threshold_mm: float) -> str:
    if delta_mm < -threshold_mm:
        return "approaching"
    if delta_mm > threshold_mm:
        return "receding"
    return "stationary"
