#!/usr/bin/env python3
"""Ask an LLM whether the robot should speak, for each vignette in vignettes/.

Usage:  python3 mvp.py [--provider anthropic|gemini] [--model MODEL] [--repeat N]
                       [--rubric 3|6] [--timeout SECONDS]
"""

import argparse
import json
import math
import os
import pathlib
import statistics
import sys
import time
from dataclasses import dataclass
from typing import List, Literal, Optional

import dotenv
from pydantic import BaseModel, Field

from context import validate

VIGNETTES = pathlib.Path(__file__).parent / "vignettes"

DEFAULT_MODEL = {
    "anthropic": "claude-haiku-4-5-20251001",
    "gemini": "gemini-3.1-flash-lite",
    "groq": "openai/gpt-oss-20b",
    "jev": "jev-latest",
}
ENV_KEY = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "jev": "TYPESAFE_API_KEY",
}
SPEAKS = ("greet", "respond")


# Field order matters in every model below: providers generate keys in schema
# order, so the rubric is scored before the action is chosen.

class Decision3(BaseModel):
    """The original MVP shape, kept so --rubric 3 can be compared against 6."""

    invitation: int = Field(ge=1, le=5, description="How much does the person invite contact?")
    interruption_cost: int = Field(ge=1, le=5, description="Cost of interrupting them now")
    ambient_fit: int = Field(ge=1, le=5, description="Would speech be heard and fit the room?")
    action: Literal["remain_silent", "wait", "greet"]
    rule_fired: str = Field(description="The single rule that most drove this choice")
    confidence: float = Field(ge=0.0, le=1.0)


class Rubric(BaseModel):
    invitation: int = Field(ge=1, le=5)
    interruption_cost: int = Field(ge=1, le=5)
    urgency: int = Field(ge=1, le=5)
    redundancy: int = Field(ge=1, le=5)
    ambient_fit: int = Field(ge=1, le=5)
    addressivity: int = Field(ge=1, le=5)


class Decision6(BaseModel):
    """schema/decision.schema.json without speech, which is a second call."""

    rubric: Rubric
    action: Literal["remain_silent", "wait", "greet", "respond"]
    category: Literal[
        "appropriate_to_initiate",
        "inappropriate_to_interrupt",
        "person_needs_assistance",
        "insufficient_evidence",
    ]
    rule_fired: str = Field(description="The single rule that most drove this choice")
    confidence: float = Field(ge=0.0, le=1.0)
    recheck_in_ms: int = Field(ge=0)


class Speech(BaseModel):
    text: str
    volume: Literal["x-soft", "soft", "medium", "loud"]
    rate: Literal["slow", "medium", "fast"]
    pitch: Literal["low", "medium", "high"]


INTRO = """You decide whether a mobile robot in a university building should speak \
to a nearby person. You are given a JSON snapshot of one moment."""

DIMENSIONS_3 = """Score three dimensions 1-5, then choose an action.

invitation        1 = ignoring the robot, 5 = clearly seeking interaction
interruption_cost 1 = idle and unoccupied, 5 = deep in work or conversation
ambient_fit       1 = speech would be inaudible or intrusive, 5 = well suited"""

DIMENSIONS_6 = """Score six dimensions 1-5, then choose an action.

invitation        1 = ignoring the robot, 5 = clearly seeking interaction
interruption_cost 1 = idle and unoccupied, 5 = deep in work or conversation
urgency           1 = nothing needs saying, 5 = appears lost or distressed
redundancy        1 = never engaged, 5 = the robot just spoke to them
ambient_fit       1 = speech would be inaudible or intrusive, 5 = well suited
addressivity      1 = unclear who to address, 5 = one clear person"""

FIELD_GUIDE = """Fields. Missing or null means not measured. Never read null as zero.

target      the one person the robot would address. null means nobody is present.
  distance_m, facing_robot, gaze_at_robot_s (seconds of sustained gaze)
  motion           approaching, leaving, passing, or stationary
  in_conversation  talking with someone else. This is what R1 reads.
  activity         idle, working, socializing, transiting, or unknown
  speech.partial_transcript  what they said, if the robot was transcribing
bystanders  other people in view. [] means nobody else.

ambient     from the microphone. Levels are dBFS: more negative is quieter.
  noise_level           quiet, moderate, or loud. Trust this word over the raw number.
  noise_floor_db        the room with nobody talking. Footsteps and carts are background,
                        and a loud floor is meant to be reported as loud.
  speech_snr_db         how far a voice rises above that floor. Large is close and clear,
                        small is distant or drowned out. null means no voice to measure.
                        Do not read a small number as someone nearby.
  speech_now            someone is talking this second.
  speech_ratio_10s      fraction of the last 10 s that contained speech. High means a
                        conversation is already underway. One remark barely moves it.
  seconds_since_speech  length of the current pause, 0 while someone is still talking.
                        null means nobody has spoken at all. That is not a long pause
                        and not "they just stopped."

robot
  is_speaking       true means ambient was not measured, because the mic would only
                    hear the robot. Its nulls mean "not measured", not a quiet room.
  engaged           the robot is already in a conversation. Transcripts only exist
                    while this is true, so an empty transcript otherwise is not silence.
  last_spoke_s_ago  seconds since the robot last spoke. null means never.
  consecutive_no_response  times this person was addressed and did not respond.

Score ambient_fit from ambient.noise_level. Quiet or moderate is audible; loud may
be inaudible. A quiet room where someone is working is still a high ambient_fit;
put the cost of speaking in interruption_cost. A high speech_ratio_10s raises
interruption_cost, but it does not by itself prove this person is in the
conversation; target.in_conversation does."""

RULES = """Rules, in priority order. A higher rule overrides a lower one.
R1 Never greet someone who is in a conversation with another person.
R2 Never greet if robot.last_spoke_s_ago is under 30, or consecutive_no_response is 2 or more.
R3 Do not greet someone moving past without facing the robot; they are in transit.
R4 Do not greet someone absorbed in work unless they look at the robot.
R5 Greet when the person faces the robot, is stationary, and is within ~3 m.
R6 When evidence is thin or contradictory, remain silent. Silence is the safe default."""

ACTIONS_3 = """Actions
remain_silent  say nothing, do not expect this to change soon
wait           a good moment may be arriving; stay ready but silent
greet          speak now

Score the three dimensions first, then pick the action consistent with them.
Set rule_fired to the rule ID and a few words, e.g. "R1 target in conversation"."""

ACTIONS_6 = """Actions
remain_silent  say nothing, do not expect this to change soon
wait           a good moment may be arriving; stay ready but silent
greet          open a new interaction now
respond        reply to something the person said to the robot. Only possible when
               target.speech.partial_transcript is present.

Categories
appropriate_to_initiate     speaking now is right
inappropriate_to_interrupt  they are busy, in transit, in conversation, or already addressed
person_needs_assistance     urgency is high
insufficient_evidence       R6: data missing or contradictory

recheck_in_ms  how long before this is worth deciding again: about 1000 if a good
               moment may be arriving, 10000 or more if nothing is likely to change.

Score the six dimensions first, then pick the action and category consistent with them.
Set rule_fired to the rule ID and a few words, e.g. "R1 target in conversation"."""

SYSTEM_3 = "\n\n".join([INTRO, DIMENSIONS_3, FIELD_GUIDE, RULES, ACTIONS_3])
SYSTEM_6 = "\n\n".join([INTRO, DIMENSIONS_6, FIELD_GUIDE, RULES, ACTIONS_6])

SPEECH_SYSTEM = """A mobile robot in a university building has decided to speak to a \
nearby person. You are given the scene and the decision.

Write one short line for it to say: under 12 words, friendly and plain. If the action \
is respond, answer what the person said. Match the room: soft when ambient.noise_level \
is quiet, medium when moderate, loud only when the room is loud."""


def load_vignettes() -> list:
    files = sorted(VIGNETTES.glob("*.json"))
    if not files:
        sys.exit("no vignettes found in %s" % VIGNETTES)
    out = []
    for f in files:
        v = json.loads(f.read_text())
        v["file"] = f.stem
        try:
            validate(v["context"], f.name)
        except ValueError as e:
            sys.exit("invalid vignette, %s" % e)
        out.append(v)
    return out


def make_client(provider: str, timeout_s: float):
    # No SDK retries: a retried call would be timed as one slow call, and the
    # robot cannot wait for a retry anyway.
    if provider == "anthropic":
        import anthropic

        return anthropic.Anthropic(max_retries=0, timeout=timeout_s)
    if provider == "gemini":
        from google import genai
        from google.genai import types

        # The SDK forwards timeout as a server deadline, and the server rejects any
        # under 10 s. Presetting the header keeps the server happy while the client
        # still gives up at timeout_s.
        return genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(
                timeout=int(timeout_s * 1000),
                headers={"X-Server-Timeout": str(max(10, math.ceil(timeout_s)))},
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    if provider == "groq":
        import httpx

        return httpx.Client(
            base_url="https://api.groq.com/openai/v1",
            headers={"Authorization": "Bearer " + os.environ["GROQ_API_KEY"]},
            timeout=timeout_s,
        )
    if provider == "jev":
        import httpx

        return httpx.Client(
            base_url="https://api.typesafe.ai/v1",
            headers={"Authorization": "Bearer " + os.environ["TYPESAFE_API_KEY"]},
            timeout=timeout_s,
        )
    raise ValueError("unknown provider: %s" % provider)


def _ask_anthropic(client, model, system, user, schema, max_tokens):
    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
    )
    return response.parsed_output, None


# Some models reject thinking_budget=0 outright (gemini-3.5-flash-lite does).
# Discovered per-model at runtime rather than hardcoded, since the list shifts.
_NO_THINKING_CONTROL = set()


def _ask_gemini(client, model, system, user, schema, max_tokens):
    from google.genai import errors, types

    def call(disable_thinking: bool):
        config = dict(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0,
            max_output_tokens=max_tokens,
        )
        if disable_thinking:
            # Gemini 3 thinks by default; this decision does not need it and the
            # latency budget cannot absorb it.
            config["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        return client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(**config),
        )

    try:
        response = call(model not in _NO_THINKING_CONTROL)
    except errors.ClientError as e:
        # A 429 is also a ClientError; only a rejected request (400) should switch
        # thinking on, or one rate limit would slow every later call. The 400 does
        # not name the thinking setting, so the model is only recorded once the
        # retry without it succeeds.
        if model in _NO_THINKING_CONTROL or getattr(e, "code", None) != 400:
            raise
        response = call(False)
        _NO_THINKING_CONTROL.add(model)
        print("note: %s rejects thinking_budget=0; leaving thinking on, which "
              "costs latency" % model, file=sys.stderr)

    usage = response.usage_metadata
    thoughts = getattr(usage, "thoughts_token_count", None) if usage else None
    if response.parsed is not None:
        return response.parsed, thoughts
    return schema.model_validate_json(response.text), thoughts


class ApiError(Exception):
    def __init__(self, code: int, body: str):
        super().__init__("%d %s" % (code, body[:300]))
        self.code = code


def _strict_schema(schema) -> dict:
    """Pydantic's JSON schema, reshaped for strict structured output: refs
    inlined, every property required, no extra keys."""
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node):
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(defs[node["$ref"].split("/")[-1]])
        node = {k: walk(v) for k, v in node.items() if k not in ("title", "default")}
        if node.get("type") == "object":
            node["additionalProperties"] = False
            node["required"] = list(node.get("properties", {}))
        return node

    return walk(raw)


# gpt-oss reasons before answering and those tokens count against the output
# limit, so the decision's own budget alone would truncate it.
GROQ_REASONING_ALLOWANCE = 1024


def _ask_groq(client, model, system, user, schema, max_tokens):
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0,
        "max_completion_tokens": max_tokens + GROQ_REASONING_ALLOWANCE,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": schema.__name__, "strict": True, "schema": _strict_schema(schema)}},
    }
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
        body["include_reasoning"] = False
    response = client.post("/chat/completions", json=body)
    if response.status_code != 200:
        raise ApiError(response.status_code, response.text)
    data = response.json()
    details = (data.get("usage") or {}).get("completion_tokens_details") or {}
    return (schema.model_validate_json(data["choices"][0]["message"]["content"]),
            details.get("reasoning_tokens"))


def _parse_block(text: str) -> dict:
    """'name  description' lines, with indented lines continuing the previous one."""
    out, name = {}, None
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        if line[0].isspace() and name:
            out[name] += " " + line.strip()
        else:
            name, _, desc = line.partition(" ")
            out[name] = desc.strip()
    return out


def _score_levels(ends: str) -> List[str]:
    """'1 = low, 5 = high' as five ordered levels."""
    low, high = ends.split(", 5 = ")
    return ["1: " + low.split("= ", 1)[1], "2", "3", "4", "5: " + high]


DIMENSION_ENDS = _parse_block("\n" + DIMENSIONS_6.split("\n\n", 1)[1])
RULE_TEXT = {line.split(" ", 1)[0]: line.split(" ", 1)[1]
             for line in RULES.splitlines()[1:] if line.strip()}
ACTION_TEXT = _parse_block(ACTIONS_6.split("\n\nCategories")[0])
CATEGORY_TEXT = _parse_block(ACTIONS_6.split("\n\n")[1])


def _ask_jev(client, model, system, user, schema, max_tokens):
    """Jev answers typed questions, not prompts, so the decision is rebuilt from
    one Score per rubric dimension plus Choices for action, rule, and category.
    Each question is evaluated in isolation, so the action does not see the scores."""
    six = schema is Decision6
    dims = list(Rubric.model_fields) if six else ["invitation", "interruption_cost", "ambient_fit"]
    actions = list(ACTION_TEXT) if six else ["remain_silent", "wait", "greet"]
    guide = {"field_guide": FIELD_GUIDE, "rules": RULES}

    questions = {d: {"type": "score",
                     "instructions": {**guide, "question": "Rate `%s` for this moment." % d},
                     "criteria": _score_levels(DIMENSION_ENDS[d])} for d in dims}
    questions["action"] = {
        "type": "choice",
        "instructions": {**guide, "question": "Which action should the robot take now? "
                         "Apply `rules` in priority order; a higher rule overrides a lower one."},
        "criteria": {a: ACTION_TEXT[a] for a in actions}}
    questions["rule_fired"] = {
        "type": "choice",
        "instructions": {**guide, "question": "Which single rule most decides this moment?"},
        "criteria": RULE_TEXT}
    if six:
        questions["category"] = {
            "type": "choice",
            "instructions": {**guide, "question": "Which category describes this moment?"},
            "criteria": CATEGORY_TEXT}

    response = client.post("/systemone", json={
        "model": model, "state": json.loads(user), "questions": questions})
    if response.status_code != 200:
        raise ApiError(response.status_code, response.text)
    answers = response.json()["answers"]

    # Score levels come back 0-indexed and probability-weighted.
    scores = {d: min(5, max(1, round(answers[d]["score"]) + 1)) for d in dims}
    action = answers["action"]
    rule = answers["rule_fired"]["choice"]
    common = dict(action=action["choice"], confidence=action["confidence"],
                  rule_fired="%s %s" % (rule, RULE_TEXT[rule]))
    if six:
        return Decision6(rubric=Rubric(**scores), category=answers["category"]["choice"],
                         recheck_in_ms=0, **common), None
    return Decision3(**scores, **common), None


ASK = {"anthropic": _ask_anthropic, "gemini": _ask_gemini, "groq": _ask_groq,
       "jev": _ask_jev}


# Set from --pace and --busy-retries. Free tiers cap requests per minute and
# shed load with 503s, so a benchmark that fires calls back to back measures
# the quota, not the model.
PACING = {"pace_s": 0.0, "busy_retries": 0}
BUSY_WAITS_S = (15, 30, 60)
BUSY_STATUS = {429, 500, 503, 504, 529}
busy_retries_used = 0
_last_call_t = None


def _status(e: BaseException) -> Optional[int]:
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    return code if isinstance(code, int) else None


def ask(provider, client, model, system, user, schema, max_tokens):
    """Returns (parsed, elapsed_ms, thought_tokens).

    Timing wraps only the successful network call. Pacing waits and busy
    retries happen outside it, so they never show up as model latency.
    """
    global busy_retries_used, _last_call_t
    fn = ASK[provider]

    for attempt in range(PACING["busy_retries"] + 1):
        if _last_call_t is not None:
            wait = PACING["pace_s"] - (time.monotonic() - _last_call_t)
            if wait > 0:
                time.sleep(wait)
        _last_call_t = time.monotonic()

        start = time.perf_counter()
        try:
            parsed, thoughts = fn(client, model, system, user, schema, max_tokens)
        except Exception as e:  # noqa: BLE001 - re-raised unless the server was busy
            if _status(e) not in BUSY_STATUS or attempt == PACING["busy_retries"]:
                raise
            wait = BUSY_WAITS_S[min(attempt, len(BUSY_WAITS_S) - 1)]
            busy_retries_used += 1
            print("  server busy (%s); waiting %ds and retrying" % (_status(e), wait),
                  file=sys.stderr)
            time.sleep(wait)
            continue
        return parsed, (time.perf_counter() - start) * 1000, thoughts


@dataclass
class Result:
    action: str
    scores: List[int]
    ms1: float
    ms2: Optional[float]
    thoughts: Optional[int]
    speech: Optional[Speech]
    speech_error: Optional[str]


def decide(provider, client, model, ctx, rubric) -> Result:
    user = json.dumps(ctx)
    if rubric == 3:
        d, ms, thoughts = ask(provider, client, model, SYSTEM_3, user, Decision3, 400)
        return Result(d.action, [d.invitation, d.interruption_cost, d.ambient_fit],
                      ms, None, thoughts, None, None)

    d, ms, thoughts = ask(provider, client, model, SYSTEM_6, user, Decision6, 400)
    speech = ms2 = speech_error = None
    # Jev only answers typed questions; it cannot write the line to say.
    if d.action in SPEAKS and provider != "jev":
        # A failed line should not cost the decision, which is what is being scored.
        try:
            speech, ms2, _ = ask(provider, client, model, SPEECH_SYSTEM,
                                 json.dumps({"context": ctx, "decision": d.model_dump()}),
                                 Speech, 150)
        except Exception as e:  # noqa: BLE001
            speech_error = "TIMEOUT" if is_timeout(e) else str(e)[:200] or type(e).__name__
    r = d.rubric
    return Result(d.action,
                  [r.invitation, r.interruption_cost, r.urgency, r.redundancy,
                   r.ambient_fit, r.addressivity],
                  ms, ms2, thoughts, speech, speech_error)


def is_timeout(e: BaseException) -> bool:
    # Each SDK wraps httpx's timeout in its own class; walk the chain for any of them.
    seen = set()
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if "timeout" in type(e).__name__.lower():
            return True
        e = e.__cause__ or e.__context__
    return False


def fmt_ms(values: List[float]) -> str:
    if not values:
        return "-"
    return "p50 %.0fms  max %.0fms  (n=%d)" % (statistics.median(values), max(values), len(values))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="anthropic", choices=sorted(DEFAULT_MODEL))
    ap.add_argument("--model", default=None, help="overrides the provider default")
    ap.add_argument("--repeat", type=int, default=1, help="passes over the set")
    ap.add_argument("--rubric", type=int, default=6, choices=[3, 6],
                    help="3 = original MVP decision, 6 = schema/decision.schema.json")
    ap.add_argument("--timeout", type=float, default=5.0, help="seconds per call")
    ap.add_argument("--pace", type=float, default=0.0,
                    help="minimum seconds between calls, to stay under a free-tier rate limit")
    ap.add_argument("--busy-retries", type=int, default=0,
                    help="retries after a 429/503, waiting 15, 30, then 60 s")
    ap.add_argument("--gentle", action="store_true",
                    help="free-tier preset: --pace 5 --busy-retries 3 --timeout 15")
    args = ap.parse_args()
    if args.gentle:
        args.pace = max(args.pace, 5.0)
        args.busy_retries = max(args.busy_retries, 3)
        args.timeout = max(args.timeout, 15.0)
    PACING["pace_s"] = args.pace
    PACING["busy_retries"] = args.busy_retries

    dotenv.load_dotenv(pathlib.Path(__file__).parent / ".env")
    key = ENV_KEY[args.provider]
    if not os.environ.get(key):
        sys.exit("%s not set. Copy .env.example to .env and add your key." % key)

    model = args.model or DEFAULT_MODEL[args.provider]
    client = make_client(args.provider, args.timeout)

    vignettes = []
    for v in load_vignettes():
        if v.get("expect"):
            vignettes.append(v)
        else:
            print("skipping %s: no expect label yet" % v["file"], file=sys.stderr)
    if not vignettes:
        sys.exit("no labelled vignettes")

    # The first call is not representative: Anthropic compiles each schema's grammar
    # server-side and caches it, and any provider may be cold. Spend throwaway calls,
    # one per schema, so the timings below mean something.
    print("warming up (%s / %s, rubric %d)..." % (args.provider, model, args.rubric),
          file=sys.stderr)
    warm_ctx = vignettes[0]["context"]
    try:
        if args.rubric == 3:
            ask(args.provider, client, model, SYSTEM_3, json.dumps(warm_ctx), Decision3, 400)
        else:
            ask(args.provider, client, model, SYSTEM_6, json.dumps(warm_ctx), Decision6, 400)
            ask(args.provider, client, model, SPEECH_SYSTEM,
                json.dumps({"context": warm_ctx, "decision": {"action": "greet"}}), Speech, 150)
    except Exception as e:  # noqa: BLE001 - a cold-start failure shouldn't end the run
        print("warm-up failed (%s: %s); continuing with cold timings"
              % (type(e).__name__, str(e)[:120]), file=sys.stderr)

    if args.rubric == 3:
        score_head, score_fmt = "inv cost fit", "%3d %4d %3d"
    else:
        score_head, score_fmt = "inv cost urg red fit addr", "%3d %4d %3d %3d %3d %4d"
    header = "%-4s %-30s %-14s %-14s %s %7s %7s" % (
        "id", "scenario", "expect", "got", score_head, "call1", "call2")
    print("\n" + header)
    print("-" * len(header))

    rows = []            # (vignette, action or None)
    ms1s, ms2s, thoughts = [], [], []
    timeouts = errors = 0
    actions_by_id = {}

    for _ in range(args.repeat):
        for v in vignettes:
            name = v["file"][4:][:30]
            try:
                r = decide(args.provider, client, model, v["context"], args.rubric)
            except Exception as e:  # noqa: BLE001 - surface, don't mask
                if is_timeout(e):
                    timeouts += 1
                    print("%-4s %-30s %-14s TIMEOUT after %.0fs"
                          % (v["id"], name, v["expect"], args.timeout))
                else:
                    errors += 1
                    print("%-4s %-30s %-14s ERROR %s: %s"
                          % (v["id"], name, v["expect"], type(e).__name__, str(e)[:120]))
                rows.append((v, None))
                continue

            rows.append((v, r.action))
            actions_by_id.setdefault(v["id"], []).append(r.action)
            ms1s.append(r.ms1)
            if r.ms2 is not None:
                ms2s.append(r.ms2)
            if r.thoughts is not None:
                thoughts.append(r.thoughts)

            ok = r.action == v["expect"]
            print("%-4s %-30s %-14s %-14s %s %7.0f %7s%s"
                  % (v["id"], name, v["expect"], r.action, score_fmt % tuple(r.scores),
                     r.ms1, "-" if r.ms2 is None else "%.0f" % r.ms2,
                     "" if ok else "   <-- disagrees"))
            if r.speech is not None:
                s = r.speech
                print("     says: \"%s\"  (%s, %s, %s)" % (s.text, s.volume, s.rate, s.pitch))
            elif r.speech_error:
                print("     speech call failed: %s" % r.speech_error)

    print("-" * len(header))
    total = len(rows)
    answered = sum(1 for _, a in rows if a is not None)
    agree = sum(1 for v, a in rows if a == v["expect"])
    false_greets = sum(1 for v, a in rows if a in SPEAKS and v["expect"] not in SPEAKS)
    greet_rows = [a for v, a in rows if v["expect"] == "greet"]
    pct = 100.0 * agree / total if total else 0
    pct_answered = 100.0 * agree / answered if answered else 0

    # A timeout is a miss on the robot, so the headline counts it; the answered
    # figure separates "the model was wrong" from "the model was late".
    print("agreement: %d/%d (%.0f%%), %d/%d of answered (%.0f%%)"
          % (agree, total, pct, agree, answered, pct_answered))
    print("false greets: %d   greet recall: %d/%d   timeouts: %d   errors: %d"
          % (false_greets, sum(1 for a in greet_rows if a == "greet"), len(greet_rows),
             timeouts, errors))
    print("call 1 (decision): %s" % fmt_ms(ms1s))
    if busy_retries_used:
        print("busy retries: %d (waits not counted in latency)" % busy_retries_used)
    if args.rubric == 6:
        print("call 2 (speech):   %s" % fmt_ms(ms2s))
    if args.repeat > 1:
        flips = sorted(i for i, acts in actions_by_id.items() if len(set(acts)) > 1)
        print("flipped across repeats: %s" % (", ".join(flips) if flips else "none"))
    if thoughts and any(thoughts):
        why = ("reasoning_effort=low" if args.provider == "groq"
               else "Thinking is on despite thinking_budget=0, and it costs latency")
        print("thinking tokens per call: mean %.0f, max %d. %s."
              % (statistics.mean(thoughts), max(thoughts), why))

    if false_greets:
        print("\nThe robot spoke when it should not have. That is the costly error;\n"
              "read those rows first.")
    if timeouts + errors:
        print("\n%d of %d calls failed. Those are not model mistakes; fix latency or\n"
              "quota before reading the agreement number as accuracy."
              % (timeouts + errors, total))
    if answered and pct_answered < 60:
        print("\nBelow 60% of answered. Read every disagreement before touching the prompt:\n"
              "systematic errors mean the rules need work, random ones are a\n"
              "bigger problem. See MVP_PLAN.md go/no-go.")


if __name__ == "__main__":
    main()
