"""Hard-rule post-filter: the rules a model answer cannot override.

No network, no API key. Runs on every decision after the LLM returns. It can
only turn speech into silence or waiting. It never makes the robot speak.

    from postfilter import enforce

    action, blocked_by = enforce(ctx, decision.action)
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from gate import DEFAULTS, greeted_recently

SPEAKS = ("greet", "respond")
MID_SENTENCE = "person mid-sentence"


def blocking_rule(
    ctx: Dict[str, Any],
    action: str,
    cfg: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """The first hard rule that forbids this action, or None."""
    if action not in SPEAKS:
        return None
    cfg = {**DEFAULTS, **(cfg or {})}
    target = ctx.get("target")
    robot = ctx.get("robot") or {}

    if target is None:
        return "no_person"
    if robot.get("is_speaking"):
        return "self_speaking"
    if int(robot.get("consecutive_no_response", 0)) >= cfg["max_ignored"]:
        return "R2 ignored twice"
    if action == "greet":
        if target.get("in_conversation"):
            return "R1 target in conversation"
        if greeted_recently(robot, cfg):
            return "R2 spoke recently"
    if action == "respond":
        speech = target.get("speech") or {}
        if not speech.get("partial_transcript"):
            return "respond without transcript"
        if speech.get("syntactically_complete") is False:
            return MID_SENTENCE
    return None


def enforce(
    ctx: Dict[str, Any],
    action: str,
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[str]]:
    """Return (action to take, rule that blocked the model's action or None)."""
    rule = blocking_rule(ctx, action, cfg)
    if rule is None:
        return action, None
    # The person is still talking to the robot, so the reply comes once they finish.
    return ("wait" if rule == MID_SENTENCE else "remain_silent"), rule
