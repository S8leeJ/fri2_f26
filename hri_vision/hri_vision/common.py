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


def sideways_mm(depth_mm: float, center_x: float, image_width: float, hfov_deg: float) -> float:
    """How far left (negative) or right of the camera axis a point is, in mm."""
    half = image_width / 2.0
    return depth_mm * (center_x - half) / half * math.tan(math.radians(hfov_deg) / 2.0)


def classify_motion(x_mm: float, z_mm: float, vx: float, vz: float,
                    min_speed_mm_s: float, max_miss_mm: float, passing_speed_mm_s: float) -> str:
    """Label a person from position and velocity on the floor, camera at the origin.

    x is sideways and z is forward. A person who walks on a path that misses the
    camera by more than max_miss_mm is passing.
    """
    speed = math.hypot(vx, vz)
    distance = math.hypot(x_mm, z_mm)
    if speed <= min_speed_mm_s or distance == 0:
        return "stationary"
    # A raised arm moves the box center sideways, but slower than a walk.
    walking = speed > passing_speed_mm_s
    miss = abs(x_mm * vz - z_mm * vx) / speed
    if walking and miss > max_miss_mm:
        return "passing"
    closing = -(x_mm * vx + z_mm * vz) / distance
    if closing > min_speed_mm_s:
        return "approaching"
    if closing < -min_speed_mm_s:
        return "receding"
    return "passing" if walking else "stationary"


def motion_label(samples, min_speed_mm_s: float, max_miss_mm: float,
                 passing_speed_mm_s: float) -> str:
    """samples: (time_s, forward_mm, sideways_mm), oldest first. "unknown" under 0.3 s."""
    vz = speed_mm_s([(t, z) for t, z, _ in samples])
    vx = speed_mm_s([(t, x) for t, _, x in samples])
    if vz is None or vx is None:
        return "unknown"
    _, z, x = samples[-1]
    return classify_motion(x, z, vx, vz, min_speed_mm_s, max_miss_mm, passing_speed_mm_s)


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


def gaze_label(face_visible: bool, turn: Optional[Tuple[float, float]],
               max_yaw: float, max_pitch: float) -> str:
    """toward_robot, away, or unknown. A limit of 0 turns that check off."""
    if not face_visible:
        return "unknown"
    if turn is None:
        return "toward_robot"
    yaw, pitch = turn
    if (max_yaw > 0 and yaw > max_yaw) or (max_pitch > 0 and pitch > max_pitch):
        return "away"
    return "toward_robot"
