#!/usr/bin/env python3
"""Ask an LLM whether the robot should speak, for each vignette in vignettes/.

Usage:  python3 mvp.py [--provider anthropic|gemini] [--model MODEL] [--repeat N]
"""

import argparse
import json
import os
import pathlib
import statistics
import sys
import time
from typing import Literal

import dotenv
from pydantic import BaseModel, Field

VIGNETTES = pathlib.Path(__file__).parent / "vignettes"

DEFAULT_MODEL = {
    "anthropic": "claude-haiku-4-5-20251001",
    "gemini": "gemini-3.1-flash-lite",
}
ENV_KEY = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


class Decision(BaseModel):
    """Field order matters: the rubric is scored before the action is chosen."""

    invitation: int = Field(ge=1, le=5, description="How much does the person invite contact?")
    interruption_cost: int = Field(ge=1, le=5, description="Cost of interrupting them now")
    ambient_fit: int = Field(ge=1, le=5, description="How well speech suits the soundscape")
    action: Literal["remain_silent", "wait", "greet"]
    rule_fired: str = Field(description="The single rule that most drove this choice")
    confidence: float = Field(ge=0.0, le=1.0)


SYSTEM = """You decide whether a mobile robot in a university building should speak \
to a nearby person. You are given a JSON snapshot of one moment.

Score three dimensions 1-5, then choose an action.

invitation        1 = ignoring the robot, 5 = clearly seeking interaction
interruption_cost 1 = idle and unoccupied, 5 = deep in work or conversation
ambient_fit       1 = speech would be intrusive or inaudible, 5 = well suited

Rules, in priority order. A higher rule overrides a lower one.
R1 Never greet someone who is in a conversation with another person.
R2 Never greet if the robot greeted recently, or was ignored twice.
R3 Do not greet someone moving past without facing the robot; they are in transit.
R4 Do not greet someone absorbed in work unless they look at the robot.
R5 Greet when the person faces the robot, is stationary, and is within ~3 m.
R6 When evidence is thin or contradictory, remain silent. Silence is the safe default.

Actions
remain_silent  say nothing, do not expect this to change soon
wait           a good moment may be arriving; stay ready but silent
greet          speak now

Score the three dimensions first, then pick the action consistent with them.
Set rule_fired to the rule ID and a few words, e.g. "R1 target in conversation"."""


def load_vignettes() -> list:
    files = sorted(VIGNETTES.glob("*.json"))
    if not files:
        sys.exit("no vignettes found in %s" % VIGNETTES)
    out = []
    for f in files:
        v = json.loads(f.read_text())
        v["file"] = f.stem
        out.append(v)
    return out


def make_client(provider: str):
    if provider == "anthropic":
        import anthropic

        return anthropic.Anthropic()
    if provider == "gemini":
        from google import genai

        return genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    raise ValueError("unknown provider: %s" % provider)


def decide_anthropic(client, model: str, context: dict):
    response = client.messages.parse(
        model=model,
        max_tokens=400,
        temperature=0,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(context)}],
        output_format=Decision,
    )
    return response.parsed_output


# Some models reject thinking_budget=0 outright (gemini-3.5-flash-lite does).
# Discovered per-model at runtime rather than hardcoded, since the list shifts.
_NO_THINKING_CONTROL = set()


def decide_gemini(client, model: str, context: dict):
    from google.genai import errors, types

    def call(disable_thinking: bool):
        config = dict(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=Decision,
            temperature=0,
            max_output_tokens=400,
        )
        if disable_thinking:
            # Gemini 3 thinks by default; this decision does not need it and the
            # latency budget cannot absorb it.
            config["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        return client.models.generate_content(
            model=model,
            contents=json.dumps(context),
            config=types.GenerateContentConfig(**config),
        )

    try:
        response = call(model not in _NO_THINKING_CONTROL)
    except errors.ClientError:
        if model in _NO_THINKING_CONTROL:
            raise
        _NO_THINKING_CONTROL.add(model)
        print("note: %s rejects thinking_budget=0; leaving thinking on, which "
              "costs latency" % model, file=sys.stderr)
        response = call(False)

    if response.parsed is not None:
        return response.parsed
    return Decision.model_validate_json(response.text)


def decide(provider: str, client, model: str, context: dict):
    """Returns (Decision, elapsed_ms). Timing wraps only the network call."""
    fn = decide_anthropic if provider == "anthropic" else decide_gemini
    start = time.perf_counter()
    result = fn(client, model, context)
    return result, (time.perf_counter() - start) * 1000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="anthropic", choices=sorted(DEFAULT_MODEL))
    ap.add_argument("--model", default=None, help="overrides the provider default")
    ap.add_argument("--repeat", type=int, default=1, help="passes over the set")
    args = ap.parse_args()

    dotenv.load_dotenv(pathlib.Path(__file__).parent / ".env")
    key = ENV_KEY[args.provider]
    if not os.environ.get(key):
        sys.exit("%s not set. Copy .env.example to .env and add your key." % key)

    model = args.model or DEFAULT_MODEL[args.provider]
    client = make_client(args.provider)
    vignettes = load_vignettes()

    # The first call is not representative: Anthropic compiles the schema grammar
    # server-side and caches it, and any provider may be cold. Spend one throwaway
    # call so the timings below mean something.
    print("warming up (%s / %s)..." % (args.provider, model), file=sys.stderr)
    try:
        decide(args.provider, client, model, vignettes[0]["context"])
    except Exception as e:  # noqa: BLE001 - a cold-start failure shouldn't end the run
        print("warm-up failed (%s: %s); continuing with cold timings"
              % (type(e).__name__, str(e)[:120]), file=sys.stderr)

    print("\n%-4s %-32s %-14s %-14s %3s %4s %3s %5s %5s"
          % ("id", "scenario", "expect", "got", "inv", "cost", "fit", "conf", "ms"))
    print("-" * 95)

    agree = total = 0
    latencies = []

    for _ in range(args.repeat):
        for v in vignettes:
            try:
                d, ms = decide(args.provider, client, model, v["context"])
            except Exception as e:  # noqa: BLE001 - surface, don't mask
                print("%-4s %-32s ERROR %s: %s"
                      % (v["id"], v["file"][4:][:32], type(e).__name__, e))
                total += 1
                continue

            latencies.append(ms)
            ok = d.action == v["expect"]
            agree += ok
            total += 1
            print("%-4s %-32s %-14s %-14s %3d %4d %3d %5.2f %5.0f%s"
                  % (v["id"], v["file"][4:][:32], v["expect"], d.action,
                     d.invitation, d.interruption_cost, d.ambient_fit,
                     d.confidence, ms, "" if ok else "   <-- disagrees"))

    print("-" * 95)
    pct = 100.0 * agree / total if total else 0
    line = "agreement: %d/%d (%.0f%%)" % (agree, total, pct)
    if latencies:
        line += "    latency p50 %.0fms  max %.0fms" % (
            statistics.median(latencies), max(latencies))
    print(line)

    if total and pct < 60:
        print("\nBelow 60%. Read every disagreement before touching the prompt:\n"
              "systematic errors mean the rules need work, random ones are a\n"
              "bigger problem. See MVP_PLAN.md go/no-go.")


if __name__ == "__main__":
    main()
