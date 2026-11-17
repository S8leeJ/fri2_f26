import json
import math
from typing import Any, Dict, Optional, Tuple

import numpy as np


def ros_time_to_float(stamp) -> float:
    return float(stamp.sec) + float(stamp.nanosec) / 1_000_000_000.0


def now_float(node) -> float:
    return node.get_clock().now().nanoseconds / 1_000_000_000.0


def speed_mm_s(samples) -> Optional[float]:
    """Least-squares slope of distance over time, in mm per second. Negative is closer.

    samples: (time_s, distance_mm) pairs, oldest first. None when they span under 0.3 s.
    """
    if len(samples) < 3:
        return None
    t = np.array([s[0] for s in samples], dtype=float)
    if t[-1] - t[0] < 0.3:
        return None
    d = np.array([s[1] for s in samples], dtype=float)
    return float(np.polyfit(t - t[0], d, 1)[0])


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


def image_x(box, image_width) -> Optional[float]:
    """Where the box center is across the image: -1 at the left edge, 0 at the center, 1 at the right edge."""
    if not image_width:
        return None
    half = float(image_width) / 2.0
    return round(((box[0] + box[2]) / 2.0 - half) / half, 3)


def merge_orientation(person: Dict[str, Any], orientation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """One /hri/vision/context person: the person context and its orientation, without the box."""
    merged = {k: v for k, v in person.items() if k != "bbox"}
    o = orientation or {}
    merged["orientation"] = o.get("orientation", "unknown")
    merged["gaze"] = o.get("gaze", "unknown")
    merged["face_visible"] = o.get("face_visible")
    merged["head_yaw"] = o.get("head_yaw")
    merged["head_pitch"] = o.get("head_pitch")
    return merged


Point = Tuple[float, float]


def head_turn(right_eye: Point, left_eye: Point, nose: Point, mouth: Point) -> Optional[Tuple[float, float]]:
    """(yaw, pitch) of a face from four keypoints in pixels, y down.

    yaw: the sideways offset of the nose from the middle of the eyes, divided by
    the eye distance. It is near 0 when the face points at the camera.
    pitch: the drop from the eyes to the nose, divided by the drop from the eyes
    to the mouth. It grows when the head tilts down.
    Both are measured along the eye line, so a head tilted to one side gives the
    same values. None when the points do not form a face.
    """
    mid_x = (right_eye[0] + left_eye[0]) / 2.0
    mid_y = (right_eye[1] + left_eye[1]) / 2.0
    ux, uy = left_eye[0] - right_eye[0], left_eye[1] - right_eye[1]
    gap = math.hypot(ux, uy)
    if gap < 1.0:
        return None
    ux, uy = ux / gap, uy / gap
    vx, vy = -uy, ux
    nx, ny = nose[0] - mid_x, nose[1] - mid_y
    drop = (mouth[0] - mid_x) * vx + (mouth[1] - mid_y) * vy
    if abs(drop) < 1.0:
        return None
    return abs(nx * ux + ny * uy) / gap, (nx * vx + ny * vy) / drop
