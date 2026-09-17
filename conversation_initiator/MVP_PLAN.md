# MVP Plan — test the hypothesis before building the system

**Supersedes, for now:** [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). That document is the full build. This one is the four days that decide whether the full build is worth doing.
**Runs on:** your laptop. No robot, no ROS, no teammates.
**Last updated:** September 17, 2026

---

## The one question this MVP answers

> Can an LLM, given a small structured JSON description of a social situation, decide whether to speak in a way that agrees with human judgment, fast enough to matter?

Everything else in the project is plumbing around that. If the answer is no, you need to know in September, not November.

## Why this touches nothing your teammates own

The MVP replaces every shared dependency with a static file:

| Real system | MVP substitute |
|---|---|
| Audio node → ambient dB, speech activity | numbers typed into a JSON file |
| Vision node → distance, gaze, bystanders | numbers typed into a JSON file |
| Fusion node → `/social_context` topic | `json.load()` |
| ROS 2 executor, launch files, colcon | a `python3` command |
| Robot speakers, TTS | `print()` |
| BWIbot | your laptop |

No ROS at all — not even a package. ROS adds sourcing, build, and executor-threading problems that test nothing about the research question. It enters in Step 5, after the hypothesis is confirmed.

Nothing here needs to be thrown away later: the vignettes become your evaluation dataset, the schema becomes the production schema, the gate becomes `gate.py`.

---

## What's already written

```
conversation_initiator/mvp/
├── mvp.py                    the whole thing, ~120 lines
├── requirements.txt
├── .env.example
└── vignettes/
    ├── 001_quiet_person_facing_stopped.json
    ├── 002_two_people_talking.json
    ├── 003_loud_room_person_far.json
    ├── 004_walking_past_not_facing.json
    ├── 005_already_greeted_ignored.json
    ├── 006_approaching_robot_directly.json
    ├── 007_sitting_working_absorbed.json
    └── 008_facing_but_in_conversation.json
```

---

## Step 1 — Make it run (~30 minutes)

```bash
cd conversation_initiator/mvp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # paste your key(s) into .env
python3 mvp.py --provider gemini      # or: --provider anthropic
```

Expected output, one row per vignette:

```
id   scenario                        expect         got            inv  cost fit  conf  ms
001  quiet_person_facing_stopped     greet          greet            4    2   5  0.88  412
002  two_people_talking              remain_silent  remain_silent    1    5   2  0.94  388
...
agreement: 7/8    latency p50 388ms  max 612ms
```

**Done when:** it prints a table without crashing, and `agreement` is a real number.

That single number is the first genuine evidence your project works. Nothing before it — not the design doc, not the implementation plan — is evidence.

### If it fails

| Error | Fix |
|---|---|
| `ANTHROPIC_API_KEY not set` | `.env` missing or key not pasted |
| `401` | Key wrong, or credit not yet redeemed |
| `TypeError` on `output_format` | SDK too old — needs `anthropic>=0.125` (verified working) |
| Slow first call (~1–2 s) | Normal. Schema grammar is compiled then cached ~24 h. Discard call #1. |

---

## Step 2 — Is it right, and is it fast? (Day 1–2)

Two independent questions; don't conflate them.

**Correctness.** You wrote `expect` in each filename before seeing any output, so the agreement number is honest. Read every disagreement and classify it:

- *The model is wrong* → the rules or rubric need work
- *You were wrong* → fix `expect`, and note it, because it means the task is genuinely ambiguous
- *Both defensible* → the most interesting case. These become your inter-rater reliability story later.

Do not tune the prompt until you've read all disagreements. The instinct is to patch the prompt after each one; that fits to noise on eight examples.

**Latency.** With n=8, p50 and max are the only meaningful statistics. Ignore p95 until you have 30+ calls. Measure on the wifi you'll demo on — campus adds 150–200 ms that your home connection hides.

Grow to **~20 vignettes** here, adding the cases you found yourself uncertain about. Write the filename first, every time.

**Done when:** ~20 vignettes, agreement ≥ 75%, p50 under 800 ms, and you can explain every disagreement.

---

## Step 3 — Add the gate (Day 3)

The gate is a pure function and needs no API key, so it's testable entirely offline. Cheapest real component in the project.

```python
def should_ask_llm(ctx, last) -> tuple[bool, str]:
    if ctx["person"] is None:              return False, "no_person"
    if ctx["robot"]["greeted_recently"]:   return False, "cooldown"
    if ctx["robot"]["consecutive_no_response"] >= 2: return False, "gave_up"
    return True, "ok"
```

Test it against a synthetic sequence of ~100 ticks (a person approaching, pausing, leaving) and measure the **suppression rate**. Target above 90%.

This is what makes the economics work: at 3 Hz an ungated system is 10,000 calls an hour, and your $500 credit is gone in a weekend. The gate isn't an optimization, it's the reason the project is affordable.

**Done when:** suppression rate > 90% on the synthetic sequence, and unit tests pass with no network.

---

## Step 4 — Second provider — DONE (Sep 17)

Gemini is wired in behind the same `decide()` signature, selected with `--provider gemini`. Same schema, same system prompt, same vignettes, no per-provider prompt tuning — which is what keeps the comparison honest.

### First real results

| Model | Agreement | p50 | max | Notes |
|---|---|---|---|---|
| `gemini-3.1-flash-lite` | 7/7 answered | 1208 ms | 15797 ms | one 503; thinking disabled |
| `gemini-3.5-flash-lite` | 7/8 | 815 ms | 1550 ms | thinking cannot be disabled |

**The hypothesis holds.** Across both runs every vignette except `003` was decided correctly by both models, including the two built to be adversarial:

- `005` (already greeted, geometry identical to `001`) scored `invitation=4`, `ambient_fit=5` — as inviting as the clear-yes case — and still chose `remain_silent`. It applied interaction history over geometry, which is exactly what that pair exists to detect.
- `008` (facing the robot while mid-conversation) returned `interruption_cost=5` and stayed silent, correctly ranking R1 above R5.

`003` is the only real disagreement, and it's the `wait` versus `remain_silent` boundary the vignette note already flagged as debatable. On reflection my `expect` is the weaker call: someone 5.6 m away in a 71 dB room is a defensible thing to stay silent about. Leave it as a documented ambiguity rather than tuning it away — cases like this are the substance of the inter-rater reliability story.

### Three things the run exposed

**Free-tier latency is unusable for benchmarking.** The 15.8 s outlier and the 503 on `gemini-3.1-flash-lite` were congestion, not model speed; identical code against `gemini-3.5-flash-lite` finished the set in 8.8 s versus 70 s. Do not report free-tier numbers as latency findings. Enable billing before the Phase 2 bake-off and expect paid numbers to be faster and much tighter.

**`gemini-3.5-flash-lite` rejects `thinking_budget=0`.** Thinking cannot be disabled on it, so you pay reasoning latency on every call whether you want it or not. `gemini-3.1-flash-lite` accepts `thinking_budget=0`, which makes the older model the better fit here — a three-field rubric does not need a reasoning budget. `mvp.py` detects the rejection at runtime, falls back, and warns instead of crashing.

**Confidence is poorly calibrated.** Values clustered between 0.85 and 1.00 on every case, including the one it got wrong. Don't build a threshold on that field without validating it against outcomes first.

### Corrected API notes

The released `google-genai` package (1.47.0) uses `client.models.generate_content` with `GenerateContentConfig`, *not* the `client.interactions.create` surface shown in Google's current docs — the documentation is ahead of the Python SDK. Thinking is controlled by `ThinkingConfig(thinking_budget=...)`, not `thinking_level`.

---

## Go / no-go, end of Day 4

| Result | Read | Do |
|---|---|---|
| Agreement ≥ 75%, p50 < 800 ms | Hypothesis holds | Proceed to `IMPLEMENTATION_PLAN.md` Phase 1 |
| Agreement ≥ 75%, p50 > 1500 ms | Right but slow | Keep going; lean harder on the gate and pre-warming. Latency is engineering. |
| Agreement < 60%, disagreements look systematic | Rules underspecified | Fix the rubric and rules. Still fixable. |
| Agreement < 60%, disagreements look random | Real problem | Stop and reconsider before building more. Talk to your advisor with the table in hand. |

The last row is why the MVP exists. Discovering it in September costs four days. Discovering it in November costs the semester.

---

## What this MVP deliberately does not do

Listed so you don't feel you've forgotten them — each is intentionally deferred:

- **ROS 2 integration** — Step 5, after go/no-go
- **SSML and TTS** — the action enum is what matters; prosody is polish
- **Langfuse tracing** — stdout is fine for 20 vignettes; Langfuse earns its place at 60+
- **Multiparty / bystanders** — one person first
- **Timeout, retry, circuit breaker** — matter on a robot, not in a script
- **Human labeling by others** — your own labels first; recruit people once the pipeline works

If you find yourself building any of these this week, you've left the MVP.

---

## Then what

Once go/no-go passes, `IMPLEMENTATION_PLAN.md` resumes at Phase 1 — and Phases 0 through 2 are largely already done, because the vignettes, schema, providers, and gate all came from here. The first genuinely new work is wrapping this in a ROS 2 node and agreeing the `/social_context` contract with your teammates.

That contract conversation goes better with a working demo behind it. "Here's the JSON I need, and here's the thing that already works when I feed it by hand" is a much easier ask than a schema proposal in the abstract.
