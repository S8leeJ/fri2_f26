# conversation_initiator

This package decides if the robot should start a conversation now.
It is the LLM decision layer of the "Read the Room" project.

The robot does not greet everyone who walks by.
Sensor nodes describe the scene as a small JSON object.
An LLM reads that object and chooses one action: `remain_silent`, `wait`, `greet`, or `respond`.
If it chooses to speak, it also gives the words and the prosody.

The design is in [`../docs/llm_decision_layer.md`](../docs/llm_decision_layer.md).
Read that first.

## Where it fits

```
audio node  ─┐
             ├─> fusion node ─> /social_context ─> [ gate ] ─> LLM ─> /initiation_decision
vision node ─┘                                                     └─> /speech_request ─> TTS
```

- The audio node measures room noise and speech. It lives in `../audio_signals_FRI_II/`.
- The vision node measures distance, facing, gaze, and motion. It is on the unmerged `swathi-vision-pipeline` branch.
- The fusion node does not exist yet.
- The gate is local code with no LLM. It skips the LLM call when nothing changed.
- The schema has no location input. `SCHEMA.md` §8 explains why: the study keeps the robot at one fixed spot. Some teammate branches build room labels. This conflict is open. See `../AGENTS.md` §5.

## What is here now

| Path | What it is |
|---|---|
| `mvp/mvp.py` | A laptop script with no ROS. It sends each vignette to an LLM and compares the answer with the expected action. |
| `mvp/vignettes/*.json` | 8 hand-written scenes. Each has an `expect` label. They use the old input shape, not v1.0. |
| `schema/` | The frozen v1.0 JSON Schemas for input and output, plus an example. |
| `SCHEMA.md` | The interface contract. It explains each field and what changed from earlier shapes. |
| `SCHEMA_COMPARISON.md` | The evidence behind the schema decisions. |
| `IMPLEMENTATION_PLAN.md` | The full build plan, phases 0 to 6. |
| `MVP_PLAN.md` | The MVP plan and the first results. |

This is not a ROS package yet.
There is no `package.xml`, `setup.py`, node, or gate.
`IMPLEMENTATION_PLAN.md` §1 shows the planned layout.

## Run the MVP

```bash
cd conversation_initiator/mvp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add the key for the provider you use
python3 mvp.py --provider anthropic
python3 mvp.py --provider gemini --model gemini-3.1-flash-lite --repeat 3
```

Options:

- `--provider`: `anthropic` (default) or `gemini`.
- `--model`: overrides the default model. The defaults are `claude-haiku-4-5-20251001` and `gemini-3.1-flash-lite`.
- `--repeat`: the number of passes over the vignettes.

The script first makes one warm-up call and does not time it.
Then it prints one row for each vignette: the expected action, the model's action, three rubric scores, confidence, and latency in ms.
At the end it prints the agreement and the p50 and max latency.
It warns if agreement is below 60%.

How it works:

- The system prompt holds rules R1 to R6 and a three-part rubric.
- The script asks for structured output with a Pydantic `Decision` model. Anthropic uses `messages.parse`. Gemini uses `response_schema`.
- For Gemini, it tries to turn thinking off. If a model rejects that, it keeps thinking on and prints a warning.

The MVP output is a smaller version of the v1.0 output.
It has 3 rubric scores, not 6.
It has no `respond`, `category`, `recheck_in_ms`, or `speech`.

## The schema files

`schema/social_context.schema.json` is the input.
It is one moment in time.
It has these blocks: `ambient` (from audio), `target` and `bystanders` (from vision), and `robot` and `recent_decisions` (from this node).
Only `schema_version` and `ambient.noise_db` are required.
`target: null` means nobody is present.

`schema/decision.schema.json` is the output.
It has these fields, in this order: a six-score `rubric`, then `action`, `category`, `rule_fired`, `confidence`, `recheck_in_ms`, and an optional `speech` block.
The order matters. The model scores the rubric before it picks the action.

`schema/example.json` holds one full input, its decision, and one minimal input.
All three are valid against the schemas.

For each field, read `SCHEMA.md`.
For a short table, read `../AGENTS.md` §3.
The schema is frozen. Ask the team before you change it.

## Planned ROS topics

From `SCHEMA.md` §1. All use `std_msgs/String` with a JSON payload.

| Topic | Direction | Payload |
|---|---|---|
| `/social_context` | fusion to initiator, 2 to 5 Hz | `social_context.schema.json` |
| `/initiation_decision` | initiator to logging | `decision.schema.json` |
| `/speech_request` | initiator to TTS | the `speech` block plus SSML |
| `/initiator_status` | initiator to all, 1 Hz | health and call counts |
