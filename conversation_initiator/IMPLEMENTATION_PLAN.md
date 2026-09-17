# conversation_initiator — Implementation Plan

**Owner:** Jenna Lee
**Component:** LLM decision layer (everything downstream of the fused context JSON)
**Design doc:** [`../docs/llm_decision_layer.md`](../docs/llm_decision_layer.md)
**Target:** Working node by Oct 22, evaluated by Nov 12, demo Dec 1
**Last updated:** September 17, 2026

This is the *how to build it* document. The *what and why* lives in the design doc. Read that first if you haven't.

---

## 0. Scope and boundaries

### In scope for this package

- Consuming a fused context JSON from a ROS 2 topic
- The gate (local, non-LLM, decides whether to even ask the model)
- The LLM call with strict structured output, across three provider backends
- Validation, rule post-filtering, timeout fallback
- Prosody enum to SSML mapping
- Langfuse tracing and the offline evaluation harness

### Explicitly NOT in scope

| Component | Owner | We consume |
|---|---|---|
| Audio feature extraction, STT | Audio node | `ambient.*`, `target.speech.*` |
| Kinect person tracking, gaze | Vision node | `target.*` geometry, `bystanders[]` |
| Localization | Existing BWI stack | nothing (deliberately — no room labels) |
| TTS audio playback | Shared | we emit SSML, someone plays it |

**The single most important rule in this plan:** we never block on another person's node. Phase 0 builds a fake publisher so this package is fully testable and near-complete before the audio and vision nodes exist.

---

## 1. Package layout

Python package (`ament_python`), unlike the C++ `ament_cmake` packages elsewhere in this repo — the LLM and Langfuse SDKs are Python-only.

```
conversation_initiator/
├── IMPLEMENTATION_PLAN.md          this file
├── README.md                       quickstart
├── package.xml                     ament_python
├── setup.py
├── setup.cfg
├── requirements.txt
├── .env.example                    API key names, no values
├── config/
│   ├── rules.yaml                  numbered politeness rules
│   ├── rubric.yaml                 six scoring dimensions
│   ├── gate.yaml                   thresholds, cooldowns
│   └── providers.yaml              model IDs, timeouts, token caps
├── conversation_initiator/
│   ├── __init__.py
│   ├── initiator_node.py           the ROS 2 node
│   ├── gate.py                     local pre-filter, no LLM
│   ├── schema.py                   one schema, three dialects
│   ├── prompt.py                   system instruction assembly
│   ├── validate.py                 schema + hard-rule post-filter
│   ├── prosody.py                  enums to SSML
│   ├── tracing.py                  Langfuse wrapper
│   └── providers/
│       ├── base.py                 DecisionProvider ABC
│       ├── anthropic_provider.py   Claude Haiku 4.5
│       ├── gemini_provider.py      Gemini 3.1 Flash-Lite
│       └── openai_provider.py      third A/B arm
├── vignettes/
│   ├── README.md                   how to author one
│   ├── 001_quiet_person_working.json
│   └── ...                         target 60–100
├── scripts/
│   ├── fake_context_publisher.py   Phase 0 lifeline
│   ├── bench_latency.py            Phase 2 bake-off
│   ├── upload_dataset.py           vignettes to Langfuse
│   └── run_experiment.py           ablations
└── test/
    ├── test_gate.py
    ├── test_schema.py
    ├── test_validate.py
    ├── test_prosody.py
    └── test_providers_contract.py
```

---

## 2. ROS 2 interface contract

**Agree this with your teammates before Sep 22.** It is the only thing that has to be settled early; everything else can change privately.

### Topics

| Topic | Direction | Type | Rate | Notes |
|---|---|---|---|---|
| `/social_context` | subscribe | `std_msgs/String` | 2–5 Hz | JSON payload, schema in design doc §4 |
| `/initiation_decision` | publish | `std_msgs/String` | on decision | full model output JSON, for logging and RViz |
| `/speech_request` | publish | `std_msgs/String` | on engage | `{"ssml": "...", "text": "...", "target_id": 0}` |
| `/initiator_status` | publish | `std_msgs/String` | 1 Hz | health, last decision, call count, credit burn |

### Why `String` and not a custom message

A custom `.msg` forces every consumer to build against this package and makes schema changes a multi-package rebuild. JSON-in-String costs one `json.loads` and lets each node evolve independently. It also means `ros2 topic pub` can inject test data by hand, which is worth a lot during integration.

Harden to custom messages after Nov 17 if there's time. There won't be.

### Parameters

```yaml
conversation_initiator:
  ros__parameters:
    provider: "anthropic"        # anthropic | gemini | openai
    dry_run: false               # log decisions, never publish speech
    gate_enabled: true
    call_timeout_ms: 800
    min_cooldown_ms: 3000
    langfuse_enabled: true
```

`dry_run` is not optional. Every live test on the robot starts with it on.

---

## 3. Environment setup

```bash
cd ~/bwi_ros2/src
# place this package here, then:
python3 -m venv ~/.venvs/initiator
source ~/.venvs/initiator/bin/activate
pip install -r requirements.txt
```

`requirements.txt`:

```
anthropic>=0.40
google-genai>=1.0
openai>=1.60
langfuse>=4.10
pydantic>=2.0
python-dotenv>=1.0
PyYAML>=6.0
```

### Secrets

Create `.env` from `.env.example`. **Add `.env` to `.gitignore` before writing a single key into it.**

```
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

The BWI robots are shared machines. Do not put keys in `~/.bashrc` on a shared robot, and do not paste them into Slack or Overleaf.

### Credits to redeem before Sep 22

| Credit | Amount | Used for |
|---|---|---|
| Anthropic | $500 | Primary decision model (Claude Haiku 4.5) |
| OpenAI | $1,000 | Third A/B arm |
| Gemini | free tier | Second A/B arm, no card needed |
| Langfuse | $100/mo × 6 | Tracing, datasets, experiments, annotation queues |
| Azure for Students | $100/yr | Speech TTS, the only engine with full SSML pitch |
| Deepgram | confirm amount | Teammate's audio node — **amount was not listed, verify** |

---

## 4. Phase 0 — Skeleton and fake data (Sep 18–22)

**Goal:** a node that runs, subscribes, and prints, with zero external dependencies and zero teammate dependencies.

### Tasks

1. `ros2 pkg create --build-type ament_python conversation_initiator`
2. `initiator_node.py` subscribing `/social_context`, logging what arrives
3. `scripts/fake_context_publisher.py` replaying JSON files from `vignettes/` on a timer, with `--rate` and `--loop`
4. Hand-author **20 vignettes** covering the five scenarios across quiet and loud conditions
5. Freeze the context schema and post it to the team channel

### Acceptance criteria

- `ros2 run conversation_initiator initiator_node` runs and logs fake context at 2 Hz
- 20 vignettes exist and validate against the frozen schema
- Teammates have acknowledged the schema in writing

### Vignette authoring rule

Each vignette is a **single decision moment**, not a sequence. Filename encodes the expectation:

```
003_two_people_talking_nearby__expect_wait.json
```

Write the filename before the JSON. It forces you to decide what correct behavior is before you can rationalize whatever the model does.

---

## 5. Phase 1 — Schema and provider adapters (Sep 23–Oct 1)

**Goal:** one schema, three providers, identical parsed output.

### The provider interface

```python
# providers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Decision:
    rubric: dict[str, int]
    action: str            # remain_silent | wait | greet | respond
    category: str
    rule_fired: str
    confidence: float
    recheck_in_ms: int
    speech: dict | None
    raw: dict
    latency_ms: float
    provider: str
    model: str

class DecisionProvider(ABC):
    @abstractmethod
    def decide(self, context: dict, timeout_ms: int) -> Decision: ...
```

Every backend returns the same `Decision`. Nothing downstream knows which model produced it — that is what makes the ablation a config change instead of a rewrite.

### Schema dialects

Write the schema once in `schema.py`, emit three dialects:

| Provider | Mechanism |
|---|---|
| Anthropic | `client.messages.parse(..., output_format=Model)`, or `output_config={"format": {"type": "json_schema", "schema": ...}}` |
| Gemini | `GenerateContentConfig(response_mime_type="application/json", response_schema=Model)` |
| OpenAI | `response_format={"type":"json_schema","json_schema":{...,"strict":true}}` |

Both Anthropic and Gemini accept a Pydantic class directly, so `schema.py` can define `Decision` once and hand the same class to both. Verified against `anthropic` 0.125.0 and `google-genai` 1.47.0.

**Design to Gemini's constraints.** It supports only a subset of JSON Schema, so keep nesting shallow and avoid constructs the other two would happily accept. Gemini is the lowest common denominator; if it validates there it validates everywhere.

### Critical per-provider settings

```python
# Anthropic — thinking is OFF unless explicitly enabled. Leave it off.
model="claude-haiku-4-5-20251001", max_tokens=400, temperature=0

# Gemini — thinks by default. Disable where the model allows it.
thinking_config=types.ThinkingConfig(thinking_budget=0), temperature=0
```

Measured on Sep 17: `gemini-3.1-flash-lite` accepts `thinking_budget=0`; `gemini-3.5-flash-lite` returns `400 INVALID_ARGUMENT` and cannot have thinking disabled. Prefer 3.1 for this workload and treat the rejection as a per-model capability discovered at runtime, since the list will shift. Note also that Google's published docs describe a newer `client.interactions.create` API with `thinking_level`; that surface is not in the released Python SDK yet, so build against `generate_content` and revisit.

Put `rubric` first in the schema. Providers generate keys in schema order, so scoring happens before the action is chosen — free chain-of-thought without a second call.

### Acceptance criteria

- All three providers return a valid `Decision` on all 20 vignettes
- Identical schema, no provider-specific prompt hacks
- `test_providers_contract.py` asserts the three return the same *shape*
- Malformed responses raise a typed error, never a bare `KeyError`

---

## 6. Phase 2 — Latency bake-off (Oct 2–8)

**Goal:** pick the production model with data, not vibes. This becomes a table in the paper.

### `scripts/bench_latency.py`

For each provider, 30 calls over the vignette set, recording TTFT and end-to-end. Report **P50 and P95** — the mean hides the tail, and the tail is what users feel.

```
provider    model                  P50_ttft  P95_ttft  P50_e2e  P95_e2e  $/1k calls  schema_fail
anthropic   claude-haiku-4-5       ...       ...       ...      ...      ...         0
gemini      gemini-3.1-flash-lite  ...       ...       ...      ...      ...         0
openai      <low-latency model>    ...       ...       ...      ...      ...         0
```

### Decision rule, committed in advance

> Choose the cheapest provider whose **P95 end-to-end is under 800 ms** with zero schema failures across the vignette set.

Writing the rule before seeing numbers stops you from rationalizing a favorite.

### Watch for

- **First call is slower.** Anthropic compiles the schema grammar and caches it 24 h. Discard the first call or report it separately.
- **Campus wifi adds 150–200 ms.** Benchmark from the robot, not your laptop.
- Published vendor benchmarks measure high-thinking and large inputs. Your numbers will be better. Cite your own.

### Acceptance criteria

- Table committed to the repo with raw JSON results
- One provider chosen, with the decision rule and evidence written down
- Runbook step: how to re-run this when a vendor ships a new model

---

## 7. Phase 3 — Gate, safety, tracing (Oct 9–15)

**Goal:** the thing that makes it safe to run on a robot near people.

### The gate

```python
# gate.py — no LLM, no network. Pure function of state.
def should_ask_llm(ctx: dict, state: GateState, cfg: dict) -> tuple[bool, str]:
    if not ctx.get("target"):
        return False, "no_person"
    if state.in_cooldown(ctx["t"]):
        return False, "cooldown"
    if ctx["robot"]["is_speaking"]:
        return False, "self_speaking"
    if ctx["robot"]["consecutive_no_response"] >= cfg["max_ignored"]:
        return False, "gave_up"
    if not state.materially_changed(ctx, cfg):
        return False, "no_material_change"
    return True, "ok"
```

`materially_changed` is the crux: distance moved > 0.3 m, or `facing_robot` flipped, or ambient dB moved > 6, or a new partial transcript arrived, or > 10 s since the last call.

Instrument it. `/initiator_status` should report the **suppression rate** — target above 90%. If the gate isn't suppressing most ticks, it isn't working.

### Safety layers, in order

1. **Timeout** at `call_timeout_ms`, default `remain_silent`. Never block the ROS executor — do the call on a worker thread and publish from the callback.
2. **Schema validation** via Pydantic. Reject on failure, default to silence.
3. **Hard-rule post-filter.** Rules the model cannot override, e.g. never `greet` when `other_speech_active` and target `in_conversation`; never speak when `consecutive_no_response >= 2`.
4. **Hysteresis.** Honor `recheck_in_ms`, floored at `min_cooldown_ms`.
5. **Credit circuit breaker.** Hard daily call cap from config. A runaway loop overnight is how a $500 credit becomes $0.

### Langfuse wiring

One trace per gate-passed tick. Span the LLM call, attach `latency_ms`, tokens, cost, chosen action, and the full context as input. Then:

- `scripts/upload_dataset.py` pushes vignettes as dataset items, `expected_output` = human label
- Failures observed on the robot get pulled into the dataset from the trace UI, becoming regression cases

This replaces the hand-rolled CSV logging in the design doc. Do not build both.

### Acceptance criteria

- Killing the network mid-run produces silence, not a crash or a hang
- Fuzzing malformed JSON into `/social_context` never crashes the node
- Gate suppression rate > 90% on a realistic replay
- Every decision appears as a Langfuse trace with latency and cost
- Daily cap enforced and tested

---

## 8. Phase 4 — Live integration (Oct 16–22)

**Goal:** swap the fake publisher for real nodes. Should be a one-line change.

### Sequence

1. Audio node alone → confirm `ambient.*` and `target.speech.*` populate
2. Vision node alone → confirm `target` geometry and `bystanders[]`
3. Both → confirm the fusion node emits schema-valid JSON at 2–5 Hz
4. Run this node with `dry_run: true` and watch decisions in Langfuse
5. Only then set `dry_run: false`

### Expect these problems

| Symptom | Likely cause |
|---|---|
| Every decision is `insufficient_evidence` | Vision node fields null or renamed |
| Gate suppresses everything | Real noise floor differs from hand-written vignettes; retune `materially_changed` |
| Decisions lag several seconds | Blocking the executor; move the call off the callback thread |
| Model always wants to greet | `ambient_fit` under-weighted; tighten rules, not the prompt's tone |

Harvest 20 real context snapshots from live logs and add them to `vignettes/`. Real data always contains field combinations you would not have invented.

### Acceptance criteria

- End-to-end on the robot with `dry_run: true` for 10 minutes, no crash
- 20 real vignettes captured
- Decisions traced with real sensor input

---

## 9. Phase 5 — Speech output (Oct 23–29)

**Goal:** the robot actually talks, at an appropriate volume.

The LLM emits **enums only**. A deterministic mapper builds SSML. The model never writes SSML.

```python
# prosody.py
SSML = '<speak><prosody volume="{v}" rate="{r}" pitch="{p}">{text}</prosody></speak>'
```

**Use Azure Speech.** AWS Polly's neural and generative voices silently ignore `pitch`; Azure supports the full SSML set, and your student credit covers it. If you must use Polly, either pick a standard voice or drop pitch from the schema — do not ship a system that appears to adapt pitch but doesn't.

Escape the text. A transcript containing `&` or `<` will produce invalid SSML and a silent failure.

### Acceptance criteria

- All 4 × 3 × 3 enum combinations produce valid, playable SSML
- Volume audibly differs between `x-soft` and `loud` on the robot's speakers
- Text with XML metacharacters is escaped and still speaks

---

## 10. Phase 6 — Evaluation (Oct 30–Nov 12)

**Goal:** the results section.

### Order of operations

1. **60–100 vignettes** total, mixing hand-authored and harvested
2. **Three or more humans label each.** Recruit teammates plus two outsiders. Outsiders matter — teammates know what the system is supposed to do and will label to match it.
3. **Human–human agreement first.** Fleiss' κ, or Krippendorff's α if counts vary. This is your ceiling and it goes in the paper regardless of what it says. If humans agree at κ=0.5, then 70% model accuracy is a good result — and you cannot claim that without this number.
4. **Adjudicate disagreements** into a reference label.
5. **Model vs reference:** accuracy, per-class precision/recall/F1, confusion matrix. Spearman's ρ for the ordinal rubric scores. The comparable HRI study reports ρ ≈ 0.82–0.83 for GPT-4 against human social intuitions; that is your yardstick.
6. **Ablations as Langfuse experiments** on the identical dataset:

| Run | Input given to the model |
|---|---|
| `full` | complete context JSON |
| `audio_only` | ambient + speech fields |
| `vision_only` | geometry + gaze fields |
| `context_unaware` | rules only, no JSON |
| `claude` / `gemini` / `openai` | full context, model swapped |

Each is a dataset run, comparable side by side in the UI. Use versioned datasets so numbers are reproducible after you inevitably add vignettes.

### Acceptance criteria

- κ reported for human–human agreement
- Confusion matrix per condition
- Cross-model comparison table
- Latency P50/P95 for the shipped configuration
- Every number regenerable by re-running one script

---

## 11. Testing strategy

| Layer | What | When |
|---|---|---|
| Unit | gate, prosody, validate, schema dialects | every commit, no network |
| Contract | three providers return the same shape | before Phase 2 |
| Replay | fake publisher over all vignettes | before every robot session |
| Fault injection | network down, malformed JSON, timeout, empty context | Phase 3 |
| Live | `dry_run: true` on the robot | Phase 4 onward |

Keep unit tests **network-free** by recording provider responses as fixtures. Tests that hit a paid API are tests you will stop running.

---

## 12. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Sensor nodes slip past Oct 22 | Blocks integration | Phase 0 fake publisher; this package reaches Phase 3 alone |
| P95 latency exceeds 800 ms on campus wifi | Feels broken | Bake-off from the robot; gate reduces call frequency; pre-warm on approach |
| Human agreement is low (κ < 0.4) | Weakens the whole evaluation | Find out in Phase 6 *early*; tighten label definitions and re-label a subset |
| Credit exhausted by a runaway loop | Project stops | Daily cap circuit breaker in Phase 3, not later |
| Vendor ships a new model mid-project | Numbers go stale | Pin model IDs in `providers.yaml`; re-run bake-off, don't drift |
| Keys leak from a shared robot | Account compromise | `.env` gitignored before first use; never in `.bashrc` on shared machines |
| Vapi absorbs the turn-taking loop | Architecture fights itself | Use Vapi only as the context-unaware baseline, not in the main path |

---

## 13. Definition of done

- [ ] Runs on the BWIbot, consuming the real fusion topic
- [ ] Median end-to-end decision latency under 800 ms, measured on-robot
- [ ] Never speaks when `other_speech_active` and the target is in conversation
- [ ] Never repeats a greeting to someone who ignored it twice
- [ ] Every decision traced in Langfuse with latency and cost
- [ ] 60+ labeled vignettes with human–human κ reported
- [ ] Four ablation conditions run on the same dataset
- [ ] Cross-model comparison across all three providers
- [ ] `README.md` lets a teammate run it from scratch in under 10 minutes
- [ ] No API key anywhere in git history

---

## 14. Immediate next actions

1. Redeem the Anthropic, Langfuse, and Azure credits — Langfuse's 6-month window starts on redemption, so don't claim it early
2. Confirm the Deepgram credit amount with the YC agent; it was the one line without a number
3. `ros2 pkg create --build-type ament_python conversation_initiator`
4. Add `.env` to `.gitignore` **before** touching any key
5. Post the frozen context schema to the team channel and get explicit acknowledgment
6. Write vignettes 1–20 by hand

Items 4 and 5 are the ones that cause real damage if skipped.
