# MVP Plan — test the hypothesis before building the system

**Supersedes, for now:** [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). That document is the full build. This one is the four days that decide whether the full build is worth doing.
**Runs on:** your laptop. No robot, no ROS, no teammates.
**Last updated:** September 22, 2026 (moved onto context schema v2.0)

---

## The one question this MVP answers

> Can an LLM, given a small structured JSON description of a social situation, decide whether to speak in a way that agrees with human judgment, fast enough to matter?

Everything else in the project is plumbing around that. If the answer is no, you need to know in September, not November.

## Why this touches nothing your teammates own

The MVP replaces every shared dependency with a static file:

| Real system | MVP substitute |
|---|---|
| Audio node → noise floor, speech activity (`ambient`, schema v2.0) | numbers typed into a JSON file |
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
├── mvp.py                    prompt, decision models, providers, benchmark table
├── context.py                schema validation + audio node adapter
├── gate.py                   local pre-filter (Step 3)
├── test_gate.py              gate and contract tests, no network
├── requirements.txt
├── .env.example
└── vignettes/                all in schema v2.0 shape
    ├── 001_quiet_person_facing_stopped.json
    ├── 002_two_people_talking.json
    ├── 003_loud_room_person_far.json
    ├── 004_walking_past_not_facing.json
    ├── 005_already_greeted_ignored.json
    ├── 006_approaching_robot_directly.json
    ├── 007_sitting_working_absorbed.json
    ├── 008_facing_but_in_conversation.json
    └── 009_robot_mid_utterance.json    unlabelled; write expect before running
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
id   scenario                       expect         got            inv cost urg red fit addr   call1   call2
001  quiet_person_facing_stopped    greet          greet            5    1   1   1   5    5     640     410
     says: "Hi there! Can I help you with anything?"  (soft, medium, medium)
002  two_people_talking             remain_silent  remain_silent    1    5   1   1   3    2     590       -
...
agreement: 7/8 (88%), 7/8 of answered (88%)
false greets: 0   greet recall: 2/2   timeouts: 0   errors: 0
call 1 (decision): p50 610ms  max 820ms  (n=8)
call 2 (speech):   p50 420ms  max 450ms  (n=2)
```

(Illustrative numbers. `--rubric 3` prints the original three scores and no call 2.)

**Done when:** it prints a table without crashing, and `agreement` is a real number.

That single number is the first genuine evidence your project works. Nothing before it — not the design doc, not the implementation plan — is evidence.

### If it fails

| Error | Fix |
|---|---|
| `ANTHROPIC_API_KEY not set` | `.env` missing or key not pasted |
| `401` | Key wrong, or credit not yet redeemed |
| `TypeError` on `output_format` | SDK too old — needs `anthropic>=0.125` (verified working) |
| Slow first call (~1–2 s) | Normal. Schema grammar is compiled then cached ~24 h. The warm-up discards it. |
| `invalid vignette, ...` | A vignette breaks schema v2.0. The message names the file and field. |
| `Minimum allowed deadline is 10s` | Gemini's server floor. `mvp.py` already sends a 10 s server deadline and times out client-side. |
| `429 RESOURCE_EXHAUSTED` | Gemini free-tier quota. Wait, or enable billing. Reported as an error, not a model miss. |

---

## Step 2 — Is it right, and is it fast? (Day 1–2)

Two independent questions; don't conflate them.

**Correctness.** You wrote `expect` in each vignette before seeing any output, so the agreement number is honest. `mvp.py` skips any vignette whose `expect` is `null`, so a new case can't leak its answer before you label it. Read every disagreement and classify it:

- *The model is wrong* → the rules or rubric need work
- *You were wrong* → fix `expect`, and note it, because it means the task is genuinely ambiguous
- *Both defensible* → the most interesting case. These become your inter-rater reliability story later.

Do not tune the prompt until you've read all disagreements. The instinct is to patch the prompt after each one; that fits to noise on eight examples.

**Agreement alone is a weak bar.** Five of the eight labelled cases are `remain_silent`, so a model that never speaks scores 62%. Read these alongside it:

- **False greets** — the robot spoke when it should not have. This is the costly error; the target is 0.
- **Greet recall** — of the cases that should greet, how many did. A model that never speaks scores 0 here.
- **Flips** — with `--repeat 3`, a vignette whose action changes between passes. Temperature 0 does not guarantee the same answer, and a case that flips is worse than one that is consistently wrong.

**Latency.** With n=8, p50 and max are the only meaningful statistics. Ignore p95 until you have 30+ calls. Measure on the wifi you'll demo on — campus adds 150–200 ms that your home connection hides.

Timeouts count as misses, because the robot can't wait for a late answer either. The summary also gives agreement over answered calls only, which separates "wrong" from "late".

Grow to **~20 vignettes** here, adding the cases you found yourself uncertain about. Write `expect` first, every time.

**Done when:** ~20 vignettes, agreement ≥ 75%, zero false greets, no flips across `--repeat 3`, call 1 p50 under 800 ms, and you can explain every disagreement.

---

## Step 3 — Add the gate — DONE (Sep 22)

Offline local pre-filter in `gate.py`. No API key. Suppresses ticks when: no person, robot speaking, gave up (≥2 ignores), cooldown (<3 s), or no material change (distance/facing/speech/noise/history). Forces a re-ask after 10 s even if the scene is static.

```bash
cd conversation_initiator/mvp
python test_gate.py          # unit tests + 100-tick approach/pause/leave sim
```

`mvp.py` does not run the gate on purpose: vignette agreement measures the *LLM*; the gate is measured separately so a high suppression rate is not confused with model accuracy.

The gate reads schema v2.0: `target` instead of `person`, `target.motion`, the audio node's `noise_level`, `noise_floor_db` and `speech_now`, and `robot.last_spoke_s_ago` against a 30 s greeting cooldown instead of a `greeted_recently` flag. `test_gate.py` also validates every vignette against the schema and checks the audio node adapter.

**Done when:** suppression rate > 90% on the synthetic sequence, and unit tests pass with no network. (Verified Sep 22 on v2.0: 20 tests pass, 91% suppressed.)

---

## Step 4 — Second provider — DONE (Sep 17)

Gemini is wired in behind the same `decide()` signature, selected with `--provider gemini`. Same schema, same system prompt, same vignettes, no per-provider prompt tuning — which is what keeps the comparison honest.

### First real results (Sep 17, before schema v2.0)

These used the old vignette shape (`person`, `ambient.noise_db`, free-text `activity`) and the three-score prompt. Some `activity` strings, like `talking_with_bystander`, came close to stating the answer, so these numbers are likely optimistic. They are kept for the record, not for comparison.

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

The SDK forwards `HttpOptions.timeout` to the server as a deadline, and the server rejects anything under 10 s. `mvp.py` sets the server deadline header to 10 s itself and keeps the 5 s cutoff on the client.

### Rerun on schema v2.0 (Sep 22, Gemini free tier, one pass each)

No Anthropic key was set, so only Gemini ran.

| Run | Answered | Agreement of answered | False greets | Call 1 p50 | Call 1 max | Failed |
|---|---|---|---|---|---|---|
| `gemini-3.1-flash-lite --rubric 3` | 5/8 | 5/5 | 0 | 2025 ms | 3091 ms | 3 timeouts (001, 003, 006) |
| `gemini-3.1-flash-lite --rubric 6` | 2/8 | 2/2 | 0 | 2524 ms | 2576 ms | 3 timeouts, then 3 × 429 quota |

What this does and does not show:

- **Every answered call was correct**, including `008` (R1 over R5) and `005` (R2 over R5) on the new fields.
- **It says nothing yet about greeting.** Both greet cases (`001`, `006`) timed out in both runs, so greet recall is untested, and so is the speech call.
- **Latency is still free-tier congestion,** as on Sep 17: p50 around 2 s and nearly half the calls past 5 s. It is not a model finding.
- **Thinking was off.** No call reported thinking tokens. The `thought_signature` warnings Gemini prints are a signature, not evidence of thinking.
- **A 429 no longer turns thinking on.** Before the fix, any client error, including a rate limit, permanently disabled `thinking_budget=0` for the rest of the run.
- `005` scored `redundancy=1` even though the robot spoke 8 s earlier; it still chose `remain_silent` via R2. Watch whether redundancy tracks `last_spoke_s_ago` once there is more data.

Next run: Anthropic with `--repeat 3` for both rubrics. It's the default provider and on paid credits, so it's the first run where latency is measurable.

---

## Go / no-go, end of Day 4

| Result | Read | Do |
|---|---|---|
Read agreement over **answered** calls here, on a paid tier. On the free tier, timeouts are congestion and don't count against the model.

| Result | Read | Do |
|---|---|---|
| Any false greets | Unsafe regardless of agreement | Read those rows first. Fix the rule or the field guide the model misread before anything else. |
| Agreement ≥ 75%, p50 < 800 ms | Hypothesis holds | Proceed to `IMPLEMENTATION_PLAN.md` Phase 1 |
| Agreement ≥ 75%, p50 800–1500 ms | Right, borderline speed | Proceed, but compare `--rubric 3` against `6`; if the three-score version is much faster at equal accuracy, use it on the robot. |
| Agreement ≥ 75%, p50 > 1500 ms | Right but slow | Keep going; lean harder on the gate and pre-warming. Latency is engineering. |
| Agreement 60–75% | Ambiguous | Classify every disagreement. If most are "both defensible", fix the labels, not the prompt, and add cases. If most are "model wrong", treat it like the row below. |
| Agreement < 60%, disagreements look systematic | Rules underspecified | Fix the rubric and rules. Still fixable. |
| Agreement < 60%, disagreements look random | Real problem | Stop and reconsider before building more. Talk to your advisor with the table in hand. |

The last row is why the MVP exists. Discovering it in September costs four days. Discovering it in November costs the semester.

---

## What this MVP deliberately does not do

Listed so you don't feel you've forgotten them — each is intentionally deferred:

- **ROS 2 integration** — Step 5, after go/no-go
- **SSML and TTS** — the speech call returns abstract enums; turning them into SSML and audio is polish
- **Langfuse tracing** — stdout is fine for 20 vignettes; Langfuse earns its place at 60+
- **Multiparty / bystanders** — one person first. Vignettes carry `bystanders[]` only to make `in_conversation` realistic.
- **Retry and circuit breaker** — matter on a robot, not in a script. The per-call timeout is in, because one hung call ruined a benchmark run.
- **Human labeling by others** — your own labels first; recruit people once the pipeline works

If you find yourself building any of these this week, you've left the MVP.

---

## Then what

Once go/no-go passes, `IMPLEMENTATION_PLAN.md` resumes at Phase 1 — and Phases 0 through 2 are largely already done, because the vignettes, schema, providers, and gate all came from here. The first genuinely new work is wrapping this in a ROS 2 node, with `context.audio_to_context()` as the starting point for the fusion step, and getting the audio and vision owners to sign off on schema v2.0.

That contract conversation goes better with a working demo behind it. "Here's the JSON I need, and here's the thing that already works when I feed it by hand" is a much easier ask than a schema proposal in the abstract.
