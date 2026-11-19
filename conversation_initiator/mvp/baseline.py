"""Rule-based baseline for the study: the published rules only, none of our system.

live_node.py --provider baseline uses it in place of Jev. It reads each
/social_context message as fusion publishes it (the vision and audio messages,
unchanged) and decides at once, 10 times a second. It does not use the scene
JSON from fusion_adapter.py, the gate, the post-filter, the target choice, the
gaze time, or the motion labels. Those are part of our system, which the study
compares against these rules.

Engagement: Webb, Giuliani and Lemaignan, RO-MAN 2022, as the ROS4HRI code
computes it (github.com/ros4hri/hri_engagement, engagement_node.py, Apache-2.0):

    gaze_AB = max(0, 1 - tan(head angle) / tan(60 deg))      robot in the person's view
    gaze_BA = max(0, 1 - tan(person angle) / tan(60 deg))    person in the camera's view
    f(d)    = ln(max_d + 1 - d) / ln(max_d + 1)              1 at 0 m, 0 at max_d
    S       = min(1, gaze_AB * gaze_BA * f(d))
    sample  = +1 if S > 0.5, else -1. Farther than max_d is -1.
    No face, or no head or body position: no sample.
    level   = from the mean of the samples in the window, with the ROS4HRI
              thresholds (Engagement.add).

When to speak: Hriscu et al., RO-MAN 2026, System 2.
    - Greet a person once when they become engaged. ROS4HRI publishes its
      ENGAGE_WITH intent at that moment.
    - Do not greet that person again until their level is disengaged.
    - Reply when the person speaks.

Our vision data is 2D, and ROS4HRI uses 3D head and body poses. These
conversions are needed to get its inputs. They add no rule:
    tan(head angle)   = head_yaw / k. k is measured on the robot (README.md).
    tan(person angle) = image_x * tan(hfov / 2).
    d                 = distance_m * sqrt(1 + tan(person angle)^2), because
                        distance_m is depth along the camera axis.
    Head tilt and the height of the face are not measured as angles, so they
    are not used.

Window: the ROS4HRI README says 2 s. Its config and code default is 10 s.
--baseline-window sets it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

UNKNOWN, DISENGAGED, ENGAGING, ENGAGED, DISENGAGING = (
    "unknown", "disengaged", "engaging", "engaged", "disengaging")

# A transcript older than this when it first arrives was said before this run.
# Same as fusion_adapter.TRANSCRIPT_FRESH_S.
TRANSCRIPT_FRESH_S = 6.0


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


def gaze_score(tan_angle: float, field_of_view_deg: float) -> float:
    return max(0.0, 1.0 - abs(tan_angle) / math.tan(math.radians(field_of_view_deg)))


def distance_factor(d: float, max_distance_m: float) -> float:
    return math.log(-d + max_distance_m + 1) / math.log(max_distance_m + 1)


def engagement_score(person: Dict[str, Any], cfg: BaselineConfig) -> Optional[float]:
    """S for one vision person. None means no sample."""
    depth, image_x, yaw = person.get("distance_m"), person.get("image_x"), person.get("head_yaw")
    if depth is None or image_x is None or yaw is None or not person.get("face_visible"):
        return None
    tan_side = image_x * math.tan(math.radians(cfg.hfov_deg) / 2.0)
    d = depth * math.sqrt(1.0 + tan_side ** 2)
    if d > cfg.max_distance_m:
        return 0.0
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
    score: Optional[float] = None
    greeted: bool = False


# (action, person id or None, reason)
Decision = Tuple[str, Optional[int], str]


@dataclass
class Baseline:
    cfg: BaselineConfig = field(default_factory=BaselineConfig)
    people: Dict[int, _Person] = field(default_factory=dict)
    last_transcript: Any = None

    def step(self, vision: Optional[Dict[str, Any]], audio: Optional[Dict[str, Any]]) -> List[Decision]:
        """One /social_context message: add one sample for each person and return what to do now.

        vision is None when the vision message is old: nobody is tracked now.
        Level changes come back as remain_silent, so the log shows them.
        """
        out: List[Decision] = []
        size = int(round(self.cfg.window_s * self.cfg.rate_hz))
        for person in (vision or {}).get("people", []):
            pid = person.get("id")
            score = engagement_score(person, self.cfg)
            if pid is None or score is None:
                continue
            p = self.people.setdefault(pid, _Person(Engagement(size)))
            p.score = round(score, 3)
            before = p.engagement.level
            level = p.engagement.add(1 if score > self.cfg.threshold else -1)
            if level == DISENGAGED:
                p.greeted = False
            if level == ENGAGED and not p.greeted:
                p.greeted = True
                out.append(("greet", pid, "engaged"))
            elif level != before:
                out.append(("remain_silent", pid, "engagement " + level))
        text = self._new_transcript(audio)
        if text:
            out.append(("respond", None, "person spoke"))
        return out

    def _new_transcript(self, audio: Optional[Dict[str, Any]]) -> Optional[str]:
        text = (audio or {}).get("transcript")
        if not text:
            return None
        # The audio node sends the last transcript again each second, with a growing age.
        # The same end of speech, within 0.5 s, is the same sentence (as fusion_adapter).
        age, stamp = audio.get("transcript_age_s"), audio.get("stamp")
        key: Any = text
        if age is not None and stamp is not None:
            key = float(stamp) - float(age)
            last = self.last_transcript
            if isinstance(last, float) and abs(key - last) < 0.5:
                return None
        elif key == self.last_transcript:
            return None
        self.last_transcript = key
        if age is not None and age > TRANSCRIPT_FRESH_S:
            return None
        return text

    def level(self, pid: Optional[int]) -> str:
        p = self.people.get(pid)
        return p.engagement.level if p else UNKNOWN

    def snapshot(self, pid: Optional[int]) -> Dict[str, Any]:
        p = self.people.get(pid)
        return {"level": self.level(pid), "score": p.score if p else None,
                "greeted": p.greeted if p else None}
