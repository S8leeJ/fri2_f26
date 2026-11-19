"""Rule-based baseline for the study: the published rules only, none of our system.

live_node.py --provider baseline uses it in place of Jev. It reads each
/social_context message as fusion publishes it (the vision and audio messages,
unchanged) and decides at once, 10 times a second. It does not use the scene
JSON from fusion_adapter.py, the gate, the post-filter, the target choice, the
gaze time, the gaze label, or the motion labels. Those are part of our system,
which the study compares against these rules.

Three published parts, in order:

1. Is the person participating now? Shi et al., IJSR 2015, participation zones.
   Both must hold:
     - The robot is in the person's gaze zone (head angle < cone, d <= 2.5 m)
       or in the person's front zone (body angle <= 60 deg, d <= 2.0 m).
     - The person is in the robot's gaze zone (side angle < cone, d <= 2.5 m)
       or in the robot's front zone (side angle <= 60 deg, d <= 2.0 m).
   Participating: sample +1. Not participating: -1. A person seen with no face
   (for example, with the back to the robot) is not participating: -1. When the
   head angle or the orientation is not measured, there is no sample.

2. Engaged long enough? ROS4HRI hri_engagement (engagement_node.py, Apache-2.0),
   the open implementation of Webb et al., RO-MAN 2022. The level comes from the
   mean of the samples in the window, with the ROS4HRI thresholds
   (Engagement.add). Webb's score itself is not used.

3. When to speak: Hriscu et al., RO-MAN 2026, System 2.
    - Greet a person once when their level becomes engaged.
    - Do not greet that person again until their level is disengaged.
    - Reply when the person speaks.

Shi et al. measure with motion capture. The vision pipeline (hri_vision) gives
the same four inputs from libraries, so this file adds no conversion of its own:
    head_angle_deg     angle between where the head points and the line to the
                       camera: MediaPipe Face Landmarker head pose.
    body_angle_deg     the same for the torso: MediaPipe Pose 3D shoulder points.
    side_deg           the person's angle from the robot's forward line, and
    floor_distance_m   the distance along the floor: ROS image_geometry with the
                       Kinect's own camera intrinsics, and the depth image.

Choices where Shi et al. are not clear, set before the study:
    - cone_deg 30: Eq. 1 reads |angle| < 30 deg. --baseline-cone changes it.
    - body_zone on: Shi et al. count the front zone. --baseline-no-body-zone
      uses the gaze zones only.
    - window_s 2: the ROS4HRI README says 2 s. Its config and code default is 10 s.
"""

from __future__ import annotations

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
    # Shi et al., Eqs. 1-3.
    cone_deg: float = 30.0
    gaze_zone_m: float = 2.5
    front_zone_deg: float = 60.0
    front_zone_m: float = 2.0
    body_zone: bool = True


def geometry(person: Dict[str, Any]) -> Optional[Tuple[float, float, float, Optional[float]]]:
    """(head angle, side angle, floor distance, body angle or None) of one vision person.
    None: not measured, so no sample."""
    head, side, d = person.get("head_angle_deg"), person.get("side_deg"), person.get("floor_distance_m")
    if None in (head, side, d) or not person.get("face_visible"):
        return None
    return float(head), abs(float(side)), float(d), person.get("body_angle_deg")


def participating(person: Dict[str, Any], cfg: BaselineConfig) -> Optional[bool]:
    """Shi et al.: both the person and the robot are in each other's gaze or front zone."""
    # face_visible is False when the face was looked for and not found, and None
    # when the orientation was not measured. With no face toward the camera, the
    # robot is in neither the person's gaze zone nor their front zone.
    if (person.get("face_visible") is False and person.get("side_deg") is not None
            and person.get("floor_distance_m") is not None):
        return False
    g = geometry(person)
    if g is None:
        return None
    head, side, d, body = g
    body_facing = cfg.body_zone and body is not None and body <= cfg.front_zone_deg
    robot_in_person_zone = ((head < cfg.cone_deg and d <= cfg.gaze_zone_m)
                            or (body_facing and d <= cfg.front_zone_m))
    person_in_robot_zone = ((side < cfg.cone_deg and d <= cfg.gaze_zone_m)
                            or (side <= cfg.front_zone_deg and d <= cfg.front_zone_m))
    return robot_in_person_zone and person_in_robot_zone


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
    participating: Optional[bool] = None
    geometry: Optional[Tuple[float, float, float, Optional[float]]] = None
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
            now_in = participating(person, self.cfg)
            if pid is None or now_in is None:
                continue
            p = self.people.setdefault(pid, _Person(Engagement(size)))
            p.participating, p.geometry = now_in, geometry(person)
            before = p.engagement.level
            level = p.engagement.add(1 if now_in else -1)
            if level == DISENGAGED:
                p.greeted = False
            if level == ENGAGED and not p.greeted:
                p.greeted = True
                out.append(("greet", pid, "engaged"))
            elif level != before:
                out.append(("remain_silent", pid, "engagement " + level))
        if self._new_transcript(audio):
            out.append(("respond", None, "person spoke"))
        return out

    def _new_transcript(self, audio: Optional[Dict[str, Any]]) -> Optional[str]:
        text = (audio or {}).get("transcript")
        # Speech to text can turn a short noise into "." or "...". That is not speech.
        if not text or not any(c.isalnum() for c in text):
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
        g = p.geometry if p else None
        return {"level": self.level(pid), "participating": p.participating if p else None,
                "head_deg": g[0] if g else None, "body_deg": g[3] if g else None,
                "side_deg": g[1] if g else None, "distance_m": g[2] if g else None,
                "greeted": p.greeted if p else None}
