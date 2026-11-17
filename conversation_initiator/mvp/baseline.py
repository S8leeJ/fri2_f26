"""Rule-based baseline for the study: greet once when a person becomes engaged.

No model, no network. live_node.py --provider baseline uses it in place of Jev.
Everything else stays the same: the scene, the gate clock, the greeting line,
the reply writers, and the voice.

When to speak: Hriscu et al., RO-MAN 2026, System 2. The robot gives one short
greeting when a person turns to face it and has not spoken. It does not greet
again until the person disengages. When the person speaks, the robot replies.

Engaged: Webb, Giuliani and Lemaignan, RO-MAN 2022, as the ROS4HRI code computes
it (github.com/ros4hri/hri_engagement, engagement_node.py, Apache-2.0):

    gaze_AB = max(0, 1 - tan(head angle) / tan(60 deg))      robot in the person's view
    gaze_BA = max(0, 1 - tan(person angle) / tan(60 deg))    person in the camera's view
    f(d)    = ln(max_d + 1 - d) / ln(max_d + 1)              1 at 0 m, 0 at max_d
    S       = min(1, gaze_AB * gaze_BA * f(d))
    sample  = +1 if S > 0.5, else -1. Farther than max_d is -1.

The level comes from the mean of the samples in the window, with the same
thresholds as ROS4HRI (Engagement.add).

From our vision data:
    tan(head angle)   = head_yaw / k. k is measured on the robot (README.md).
    tan(person angle) = image_x * tan(hfov / 2).
    d                 = distance_m * sqrt(1 + tan(person angle)^2), because
                        distance_m is depth along the camera axis.

Our changes to the ROS4HRI code, set before the study:
    - window_s: 2 s, not 10 s (the ROS4HRI README value).
    - A face that is not visible adds no sample, as in ROS4HRI. The old level
      stays when a person turns away. no_face = "away" counts it as -1 instead.
    - A head tilted down past pitch_limit gives gaze_AB = 0. ROS4HRI uses one
      3D head angle. We have a yaw angle and a pitch ratio.
    - Height differences between the camera and the face are ignored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

UNKNOWN, DISENGAGED, ENGAGING, ENGAGED, DISENGAGING = (
    "unknown", "disengaged", "engaging", "engaged", "disengaging")

# A person not seen for this long is forgotten. Same as fusion_adapter.LOST_TARGET_S.
FORGET_S = 5.0


@dataclass
class BaselineConfig:
    window_s: float = 2.0
    rate_hz: float = 10.0
    # Not measured yet. See README.md, "Rule-based baseline".
    k: float = 0.4
    hfov_deg: float = 90.0
    field_of_view_deg: float = 60.0
    max_distance_m: float = 4.0
    threshold: float = 0.5
    pitch_limit: float = 0.70
    no_face: str = "skip"  # "skip": add no sample, as ROS4HRI does. "away": count as -1.


def gaze_score(tan_angle: float, field_of_view_deg: float) -> float:
    return max(0.0, 1.0 - abs(tan_angle) / math.tan(math.radians(field_of_view_deg)))


def distance_factor(d: float, max_distance_m: float) -> float:
    return math.log(-d + max_distance_m + 1) / math.log(max_distance_m + 1)


def engagement_score(person: Dict[str, Any], cfg: BaselineConfig) -> Optional[float]:
    """S for one vision person. None means no sample."""
    depth = person.get("distance_m")
    if depth is None:
        return None
    if not person.get("face_visible"):
        return None if cfg.no_face == "skip" else 0.0
    tan_side = (person.get("image_x") or 0.0) * math.tan(math.radians(cfg.hfov_deg) / 2.0)
    # distance_m is depth along the camera axis. The score uses the straight-line distance.
    d = depth * math.sqrt(1.0 + tan_side ** 2)
    if d > cfg.max_distance_m:
        return 0.0
    pitch = person.get("head_pitch")
    if pitch is not None and cfg.pitch_limit > 0 and pitch > cfg.pitch_limit:
        return 0.0
    # No head points with a visible face: vision calls this toward_robot too.
    yaw = person.get("head_yaw") or 0.0
    gaze_ab = gaze_score(yaw / cfg.k, cfg.field_of_view_deg)
    gaze_ba = gaze_score(tan_side, cfg.field_of_view_deg)
    return min(1.0, gaze_ab * gaze_ba * distance_factor(d, cfg.max_distance_m))


class Engagement:
    """One person's samples and level. The levels follow ROS4HRI compute_engagement."""

    def __init__(self, size: int):
        self.size = max(2, size)
        self.min_samples = int(0.5 * self.size)
        self.history: list = []
        self.level = UNKNOWN

    def add(self, sample: int) -> str:
        self.history = (self.history + [sample])[-self.size:]
        if len(self.history) < self.min_samples:
            return self.level
        mean = sum(self.history) / len(self.history)
        level = self.level
        if level == UNKNOWN:
            level = DISENGAGED
        elif level == DISENGAGED:
            if mean > -0.4:
                level = ENGAGING
        elif level == ENGAGING:
            if mean < -0.6:
                level = DISENGAGED
            elif mean > 0.5:
                level = ENGAGED
        elif level == ENGAGED:
            if mean < 0.4:
                level = DISENGAGING
        elif level == DISENGAGING:
            if mean > 0.6:
                level = ENGAGED
            elif mean < -0.5:
                level = DISENGAGED
        self.level = level
        return level


@dataclass
class _Person:
    engagement: Engagement
    last_seen: float
    armed: bool = True
    score: Optional[float] = None


@dataclass
class Baseline:
    cfg: BaselineConfig = field(default_factory=BaselineConfig)
    people: Dict[int, _Person] = field(default_factory=dict)

    def update(self, vision: Optional[Dict[str, Any]], now: float) -> None:
        """Add one sample for each person in a fresh vision message."""
        if vision is not None and (vision.get("sensor_status") or {}).get("orientation_fresh"):
            size = int(round(self.cfg.window_s * self.cfg.rate_hz))
            for person in vision.get("people", []):
                pid = person.get("id")
                score = engagement_score(person, self.cfg)
                if pid is None or score is None:
                    continue
                p = self.people.setdefault(pid, _Person(Engagement(size), now))
                p.last_seen, p.score = now, round(score, 3)
                if p.engagement.add(1 if score > self.cfg.threshold else -1) == DISENGAGED:
                    p.armed = True
        for pid in [pid for pid, p in self.people.items() if now - p.last_seen > FORGET_S]:
            del self.people[pid]

    def level(self, pid: Optional[int]) -> str:
        p = self.people.get(pid)
        return p.engagement.level if p else UNKNOWN

    def decide(self, ctx: Dict[str, Any], pid: Optional[int]) -> Tuple[str, str]:
        """(action, reason) for the target person."""
        target = ctx.get("target")
        if target is None:
            return "remain_silent", "no person"
        if ((target.get("speech") or {}).get("partial_transcript")):
            return "respond", "person spoke"
        if any(turn.get("speaker") == "person" for turn in ctx.get("conversation") or []):
            return "remain_silent", "in conversation"
        p = self.people.get(pid)
        if p is None or p.engagement.level != ENGAGED:
            return "remain_silent", "engagement " + self.level(pid)
        if not p.armed:
            return "remain_silent", "already greeted"
        return "greet", "engaged, has not spoken"

    def greeted(self, pid: Optional[int]) -> None:
        """Call when the greeting is said. The next one waits until the person disengages."""
        p = self.people.get(pid)
        if p is not None:
            p.armed = False

    def snapshot(self, pid: Optional[int]) -> Dict[str, Any]:
        p = self.people.get(pid)
        return {"level": self.level(pid), "score": p.score if p else None,
                "armed": p.armed if p else None}
