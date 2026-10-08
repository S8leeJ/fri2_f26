"""Turn the fusion node's wrapper message into a v2.0 /social_context context.

No ROS, no network. live_node.py calls this on every tick.

    from fusion_adapter import Memory, fusion_to_context, apply_result

    mem = Memory()
    ctx = fusion_to_context(wrapper, mem, now)   # also updates mem
    ...                                          # gate, LLM, post-filter
    apply_result(mem, action, reason, line, now)

fusion/fusion_publisher.py publishes the newest audio and vision messages
unchanged, so this module owns the mapping to the schema:

    {"t", "audio": {...audio_builder JSON...}, "audio_age_s",
          "vision": {"people": [...], "sensor_status": {...}}, "vision_age_s"}

Vision does not measure in_conversation, activity or bearing_deg, so they are
left out. The robot, recent_decisions and conversation blocks come from Memory,
because the initiator owns them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from context import AMBIENT_FIELDS, SCHEMA_VERSION

VISION_STALE_S = 2.0
AUDIO_STALE_S = 3.0
# A transcript older than this when first seen is left over from before; skip it.
TRANSCRIPT_FRESH_S = 6.0
# A transcript waits this long for the gate to let an LLM call through.
PENDING_MAX_S = 15.0
NO_REPLY_S = 8.0
LOST_TARGET_S = 10.0
# The current target stays the target unless someone else is this much nearer.
TARGET_STICKY_M = 0.5
MAX_IGNORED = 2
MAX_RECENT = 5
MAX_CONVERSATION = 20

MOTION = {"approaching": "approaching", "receding": "leaving", "stationary": "stationary"}


@dataclass
class Memory:
    """State the initiator keeps between ticks."""

    target_id: Optional[int] = None
    last_target_t: Optional[float] = None
    gaze_since: Dict[int, float] = field(default_factory=dict)

    last_utterance_end: Optional[float] = None
    last_transcript: Optional[str] = None
    pending: Optional[Dict[str, Any]] = None

    engaged: bool = False
    speaking: bool = False
    last_spoke_t: Optional[float] = None
    last_utterance: Optional[str] = None
    no_response: int = 0
    awaiting_reply_since: Optional[float] = None

    last_decision_t: Optional[float] = None
    recent: List[Tuple[float, str, Optional[str]]] = field(default_factory=list)
    conversation: List[Tuple[float, str, str]] = field(default_factory=list)

    def end_interaction(self) -> None:
        self.target_id = None
        self.engaged = False
        self.no_response = 0
        self.awaiting_reply_since = None
        self.pending = None
        self.conversation = []


def _fresh(msg: Dict[str, Any], name: str, limit: float) -> Optional[Dict[str, Any]]:
    data, age = msg.get(name), msg.get(name + "_age_s")
    if not isinstance(data, dict) or age is None or age > limit:
        return None
    return data


def _pick_target(people: List[Dict[str, Any]], current: Optional[int]) -> Optional[Dict[str, Any]]:
    if not people:
        return None
    nearest = min(people, key=lambda p: p["distance_m"])
    for p in people:
        if p.get("id") == current and p["distance_m"] <= nearest["distance_m"] + TARGET_STICKY_M:
            return p
    return nearest


def _gaze_s(person: Dict[str, Any], mem: Memory, now: float, orientation_fresh: bool) -> Optional[float]:
    pid = person.get("id")
    if not orientation_fresh:
        mem.gaze_since.pop(pid, None)
        return None
    # The orientation node writes "unknown" when no face is seen, so with fresh
    # orientation it means "not looking".
    if person.get("gaze") != "toward_robot":
        mem.gaze_since.pop(pid, None)
        return 0.0
    since = mem.gaze_since.setdefault(pid, now)
    return round(now - since, 1)


def _vision_target(person: Dict[str, Any], mem: Memory, now: float, orientation_fresh: bool) -> Dict[str, Any]:
    target: Dict[str, Any] = {
        "distance_m": float(person["distance_m"]),
        "facing_robot": person.get("orientation") == "facing_robot",
    }
    gaze = _gaze_s(person, mem, now, orientation_fresh)
    if gaze is not None:
        target["gaze_at_robot_s"] = gaze
    motion = MOTION.get(person.get("direction"))
    if motion:
        target["motion"] = motion
    if person.get("dwell_time_s") is not None:
        target["dwell_s"] = float(person["dwell_time_s"])
    return target


def _note_transcript(audio: Dict[str, Any], mem: Memory, now: float) -> None:
    text = audio.get("transcript") or None
    if text is None:
        return
    age = audio.get("transcript_age_s")
    stamp = audio.get("stamp")
    if age is not None and stamp is not None:
        end = float(stamp) - float(age)
        if mem.last_utterance_end is not None and abs(end - mem.last_utterance_end) < 0.5:
            return
        if age > TRANSCRIPT_FRESH_S:
            mem.last_utterance_end = end
            return
        mem.last_utterance_end = end
    elif text == mem.last_transcript:
        return
    mem.last_transcript = text
    mem.pending = {"t": now, "text": text, "complete": audio.get("syntactically_complete")}
    mem.no_response = 0
    mem.awaiting_reply_since = None
    _add_turn(mem, now, "person", text)


def _add_turn(mem: Memory, now: float, speaker: str, text: str) -> None:
    mem.conversation = (mem.conversation + [(now, speaker, text)])[-MAX_CONVERSATION:]


def _ago(now: float, t: float) -> float:
    return round(max(0.0, now - t), 1)


def fusion_to_context(msg: Dict[str, Any], mem: Memory, now: float) -> Dict[str, Any]:
    """Build one v2.0 context from a fusion wrapper. Updates mem."""
    audio = _fresh(msg, "audio", AUDIO_STALE_S)
    vision = _fresh(msg, "vision", VISION_STALE_S)

    people = [p for p in (vision or {}).get("people", [])
              if isinstance(p, dict) and p.get("distance_m") is not None]
    chosen = _pick_target(people, mem.target_id)
    orientation_fresh = bool(((vision or {}).get("sensor_status") or {}).get("orientation_fresh"))

    if chosen is not None:
        if mem.target_id is not None and chosen.get("id") != mem.target_id:
            mem.end_interaction()
        mem.target_id = chosen.get("id")
        mem.last_target_t = now
    elif mem.last_target_t is not None and now - mem.last_target_t > LOST_TARGET_S:
        mem.end_interaction()
        mem.last_target_t = None

    if audio is not None and chosen is not None:
        _note_transcript(audio, mem, now)
    if mem.pending is not None and now - mem.pending["t"] > PENDING_MAX_S:
        mem.pending = None

    if mem.awaiting_reply_since is not None and now - mem.awaiting_reply_since > NO_REPLY_S:
        mem.no_response += 1
        mem.awaiting_reply_since = None
        if mem.no_response >= MAX_IGNORED:
            mem.engaged = False

    target = None
    if chosen is not None:
        target = _vision_target(chosen, mem, now, orientation_fresh)
        if mem.pending is not None:
            target["speech"] = {
                "detected": True,
                "partial_transcript": mem.pending["text"],
                "syntactically_complete": mem.pending["complete"],
            }

    ctx: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "t": now,
        "ambient": {k: audio[k] for k in AMBIENT_FIELDS if k in audio} if audio else {},
        "target": target,
        "bystanders": [
            {"distance_m": float(p["distance_m"]), "facing_robot": p.get("orientation") == "facing_robot"}
            for p in people if p is not chosen
        ] if vision is not None else [],
        "robot": {
            "is_speaking": mem.speaking or bool((audio or {}).get("robot_speaking")),
            "engaged": mem.engaged,
            "last_spoke_s_ago": None if mem.last_spoke_t is None else _ago(now, mem.last_spoke_t),
            "last_utterance": mem.last_utterance,
            "consecutive_no_response": mem.no_response,
        },
        "recent_decisions": [
            {"s_ago": _ago(now, t), "action": a, "reason": r} for t, a, r in mem.recent
        ],
        "conversation": [
            {"speaker": s, "text": text, "s_ago": _ago(now, t)} for t, s, text in mem.conversation
        ],
    }
    if mem.last_decision_t is not None:
        ctx["since_last_decision_s"] = _ago(now, mem.last_decision_t)
    return ctx


def consume_pending(mem: Memory) -> None:
    """Call when an LLM call starts, so the same transcript is answered once."""
    mem.pending = None


def apply_result(mem: Memory, action: str, reason: Optional[str], line: Optional[str], now: float) -> None:
    """Record a decision. line is what the robot said, or None."""
    mem.recent = ([(now, action, reason)] + mem.recent)[:MAX_RECENT]
    mem.last_decision_t = now
    if line:
        mem.last_spoke_t = now
        mem.last_utterance = line
        mem.engaged = True
        mem.awaiting_reply_since = now
        _add_turn(mem, now, "robot", line)
