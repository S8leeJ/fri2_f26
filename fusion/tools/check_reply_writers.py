#!/usr/bin/env python3
"""Check which LLM writes the robot's replies with --provider jev, and in which order.

    python3 ~/fri2_f26/fusion/tools/check_reply_writers.py

Jev cannot write sentences, so another LLM writes each reply: Groq first, then
Anthropic, then Gemini, for each one that has a key in
conversation_initiator/mvp/.env. If a call fails, the next one is tried.

It runs two tests, and makes one real call for each provider that it tries:

    1. Normal: Groq answers, and no other provider is tried.
    2. Groq key broken on purpose: Groq fails, then Anthropic answers.

The broken key exists only inside this script. The .env file does not change.
"""

import os
import sys
from pathlib import Path

MVP = Path(__file__).resolve().parents[2] / "conversation_initiator" / "mvp"
sys.path.insert(0, str(MVP))

import dotenv  # noqa: E402

dotenv.load_dotenv(MVP / ".env")

import mvp  # noqa: E402

tried = []
real_ask = mvp.ask


def logged_ask(provider, *args, **kwargs):
    try:
        out = real_ask(provider, *args, **kwargs)
        tried.append("%s ✅ %d ms" % (provider, out[1]))
        return out
    except Exception as e:
        tried.append("%s ❌ %s" % (provider, str(e)[:70]))
        raise


# line_to_say looks up ask in the mvp module, so this records every attempt.
mvp.ask = logged_ask

CTX = {"schema_version": "2.0", "ambient": {"noise_level": "quiet"},
       "target": {"distance_m": 1.2, "facing_robot": True,
                  "speech": {"detected": True, "partial_transcript": "Where is the elevator?",
                             "syntactically_complete": True}},
       "robot": {"is_speaking": False, "consecutive_no_response": 0}}
DECISION = mvp.Decision6(
    rubric=dict(invitation=4, interruption_cost=1, urgency=2, redundancy=1,
                ambient_fit=4, addressivity=4),
    action="respond", category="person_needs_assistance", rule_fired="R4",
    confidence=0.9, recheck_in_ms=0)


def run(label):
    tried.clear()
    mvp._reply_writers = None
    print(label, "order:", [w[0] for w in mvp.reply_writers()])
    speech, _, error = mvp.line_to_say("jev", None, None, CTX, DECISION)
    for attempt in tried:
        print("   tried", attempt)
    print("   says:", speech.text if speech else None, "| error:", error)


if __name__ == "__main__":
    if not mvp.reply_writers():
        sys.exit("No GROQ_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY in %s" % (MVP / ".env"))
    run("1. Normal:")
    os.environ["GROQ_API_KEY"] = "gsk_wrong_on_purpose"
    run("2. Groq key broken on purpose:")
