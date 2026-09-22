"""The /social_context contract, on the MVP side.

    from context import validate, audio_to_context

    validate(ctx)                        # raises ValueError if ctx breaks the schema
    ctx = audio_to_context(audio_json)   # one audio_builder.py object -> a v2.0 context

The schema itself lives in ../schema/social_context.schema.json; SCHEMA.md is the
human version. Nothing here duplicates a field list except the audio mapping,
which has no other home.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, Optional

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "schema" / "social_context.schema.json"
)
SCHEMA_VERSION = "2.0"

# audio_builder.py field names that go into ambient unchanged.
AMBIENT_FIELDS = (
    "noise_floor_db",
    "noise_level",
    "speech_snr_db",
    "speech_now",
    "speech_ratio_10s",
    "seconds_since_speech",
)

_validator: Optional[Draft202012Validator] = None


def _get_validator() -> Draft202012Validator:
    global _validator
    if _validator is None:
        _validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text()))
    return _validator


def validate(ctx: Dict[str, Any], name: str = "context") -> None:
    """Raise ValueError naming the first problem, or return None if ctx is valid."""
    err = best_match(_get_validator().iter_errors(ctx))
    if err is None:
        return
    where = "/".join(str(p) for p in err.absolute_path) or "(top level)"
    raise ValueError("%s: %s at %s" % (name, err.message, where))


def audio_to_context(
    audio: Dict[str, Any],
    target: Optional[Dict[str, Any]] = None,
    robot: Optional[Dict[str, Any]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a v2.0 context from one audio_builder.py object.

    target and robot come from other nodes; pass them when you have them.
    extra is copied to the top level (bystanders, recent_decisions, ...).
    """
    ctx: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "t": audio.get("stamp"),
        "ambient": {k: audio.get(k) for k in AMBIENT_FIELDS},
        "target": None,
        "robot": {
            **(robot or {}),
            "is_speaking": bool(audio.get("robot_speaking")),
            "engaged": bool(audio.get("engaged")),
        },
        **extra,
    }

    if target is not None:
        target = dict(target)
        # The audio node sends "" when there is nothing; the schema's null means the same.
        transcript = audio.get("transcript") or None
        if transcript is not None:
            target["speech"] = {
                **(target.get("speech") or {}),
                "detected": True,
                "partial_transcript": transcript,
            }
        ctx["target"] = target

    return ctx
