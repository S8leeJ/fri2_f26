"""Local pre-filter: decide whether to call the LLM at all.

No network, no API key. Pure function of the current context plus a little
remembered state. The goal is to suppress the vast majority of ticks so a
3 Hz fusion stream does not burn the credit budget.

Reads schema v2.0 contexts (../schema/social_context.schema.json).

Usage from other modules:

    from gate import GateState, should_ask_llm, note_asked

    state = GateState()
    ok, reason = should_ask_llm(ctx, state)
    if ok:
        decision = call_llm(ctx)
        note_asked(state, ctx, now=ctx.get("t", 0.0))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


# Defaults match IMPLEMENTATION_PLAN / MVP_PLAN Step 3.
DEFAULTS: Dict[str, Any] = {
    "max_ignored": 2,          # consecutive_no_response at or above → give up
    "min_cooldown_sec": 3.0,   # floor between LLM calls
    "distance_delta_m": 0.3,   # material change: person moved this far
    "noise_delta_db": 6.0,     # material change: noise floor jumped this much
    "max_stale_sec": 10.0,     # force a re-ask even if nothing else changed
    "greet_cooldown_sec": 30.0,  # last_spoke_s_ago under this = greeted recently (R2)
}


@dataclass
class GateState:
    """Remembered across ticks. Owned by whoever runs the loop."""

    last_asked_t: Optional[float] = None
    last_ctx: Optional[Dict[str, Any]] = None
    asks: int = 0
    suppressions: Dict[str, int] = field(default_factory=dict)

    def record_suppression(self, reason: str) -> None:
        self.suppressions[reason] = self.suppressions.get(reason, 0) + 1

    @property
    def ticks_seen(self) -> int:
        return self.asks + sum(self.suppressions.values())

    @property
    def suppression_rate(self) -> float:
        total = self.ticks_seen
        if total == 0:
            return 0.0
        return 1.0 - (self.asks / total)


def _t(ctx: Dict[str, Any]) -> float:
    return float(ctx.get("t") or 0.0)


def _target(ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return ctx.get("target")


def _robot(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return ctx.get("robot") or {}


def _ambient(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return ctx.get("ambient") or {}


def greeted_recently(robot: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    last = robot.get("last_spoke_s_ago")
    return last is not None and float(last) < cfg["greet_cooldown_sec"]


def _moved(a: Dict[str, Any], a0: Dict[str, Any], key: str, delta: float) -> bool:
    # Only compare numbers that were measured both times; null means not measured,
    # and a reading appearing or disappearing is caught by noise_level instead.
    x, x0 = a.get(key), a0.get(key)
    return x is not None and x0 is not None and abs(float(x) - float(x0)) >= delta


def materially_changed(
    ctx: Dict[str, Any],
    prev: Optional[Dict[str, Any]],
    cfg: Optional[Dict[str, Any]] = None,
) -> bool:
    """True if the scene moved enough that a new decision might differ."""
    cfg = {**DEFAULTS, **(cfg or {})}
    if prev is None:
        return True

    p, p0 = _target(ctx), _target(prev)
    if (p is None) != (p0 is None):
        return True
    if p is not None and p0 is not None:
        if abs(float(p.get("distance_m", 0)) - float(p0.get("distance_m", 0))) >= cfg[
            "distance_delta_m"
        ]:
            return True
        if bool(p.get("facing_robot")) != bool(p0.get("facing_robot")):
            return True
        if bool(p.get("in_conversation")) != bool(p0.get("in_conversation")):
            return True
        if p.get("motion") != p0.get("motion"):
            return True

    a, a0 = _ambient(ctx), _ambient(prev)
    if a.get("noise_level") != a0.get("noise_level"):
        return True
    if _moved(a, a0, "noise_floor_db", cfg["noise_delta_db"]):
        return True
    if _moved(a, a0, "noise_db", cfg["noise_delta_db"]):
        return True
    if bool(a.get("speech_now")) != bool(a0.get("speech_now")):
        return True
    if bool(a.get("other_speech_active")) != bool(a0.get("other_speech_active")):
        return True

    r, r0 = _robot(ctx), _robot(prev)
    if bool(r.get("is_speaking")) != bool(r0.get("is_speaking")):
        return True
    if greeted_recently(r, cfg) != greeted_recently(r0, cfg):
        return True
    if int(r.get("consecutive_no_response", 0)) != int(
        r0.get("consecutive_no_response", 0)
    ):
        return True

    return False


def should_ask_llm(
    ctx: Dict[str, Any],
    state: GateState,
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Return (ask?, reason). reason is 'ok' only when ask is True."""
    cfg = {**DEFAULTS, **(cfg or {})}
    now = _t(ctx)
    robot = _robot(ctx)

    if _target(ctx) is None:
        return False, "no_person"

    if robot.get("is_speaking"):
        return False, "self_speaking"

    if int(robot.get("consecutive_no_response", 0)) >= cfg["max_ignored"]:
        return False, "gave_up"

    if state.last_asked_t is not None:
        if now - state.last_asked_t < cfg["min_cooldown_sec"]:
            return False, "cooldown"

    # Greeting recently alone is not a hard block — it is a soft signal the LLM
    # also sees (R2) — but combined with no material change it should not re-fire
    # every tick. Handled below via materially_changed + cooldown.

    stale = (
        state.last_asked_t is not None
        and (now - state.last_asked_t) >= cfg["max_stale_sec"]
    )
    if not stale and not materially_changed(ctx, state.last_ctx, cfg):
        return False, "no_material_change"

    return True, "ok"


def note_asked(
    state: GateState,
    ctx: Dict[str, Any],
    now: Optional[float] = None,
) -> None:
    """Call after a successful (or attempted) LLM invoke that passed the gate."""
    state.asks += 1
    state.last_asked_t = float(now if now is not None else _t(ctx))
    state.last_ctx = ctx


def decide_tick(
    ctx: Dict[str, Any],
    state: GateState,
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Convenience: should_ask_llm + bookkeeping for suppressions / asks.

    Updates state for suppressions always; call note_asked yourself only if
    you actually invoke the model (so a dry-run gate sim can count asks
    without a network call by passing record_ask=True below).
    """
    ok, reason = should_ask_llm(ctx, state, cfg)
    if not ok:
        state.record_suppression(reason)
    return ok, reason
