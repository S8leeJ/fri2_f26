# AGENTS.md

This file tells AI agents how this repo is built and how to work in it.
Read it before you explore the code.
It summarizes and points to other docs. It does not replace them.

Last checked against the code: September 22, 2026, on `main` at `be973ef`.

---

## 1. Orientation

This repo is "Read the Room," a UT Austin FRI research project.
The robot is a BWIbot on ROS 2 Humble.
The research question: can an LLM decide when it is polite for a robot to start a conversation?
The LLM gets a small JSON description of the scene. It returns a structured decision.

The repo has three unrelated parts:

| Part | Directories | Language | Status |
|---|---|---|---|
| FRI homework stack | `follower_robot/`, `nav_goals/`, `spatial_transforms/`, `spatial_utils/` | C++, `ament_cmake` | Finished homework. Not used by the study. |
| LLM decision layer | `conversation_initiator/` | Python | Offline MVP works. ROS node not started. |
| Audio subsystem | `audio_signals_FRI_II/` | Python | Runs standalone. No ROS node yet. |

Most future work touches `conversation_initiator/` and `audio_signals_FRI_II/`.
The homework packages are old. Do not change them unless a person asks.
The study runs the robot at one fixed spot, so the navigation code has no part in it (`conversation_initiator/SCHEMA_COMPARISON.md` §6).

Key docs, in reading order:

1. [`docs/llm_decision_layer.md`](docs/llm_decision_layer.md): the design. It covers the architecture, rubric, rules, output schema, and evaluation plan.
2. [`conversation_initiator/SCHEMA.md`](conversation_initiator/SCHEMA.md): the frozen v1.0 interface contract.
3. [`conversation_initiator/IMPLEMENTATION_PLAN.md`](conversation_initiator/IMPLEMENTATION_PLAN.md): the build plan, phases 0 to 6.
4. [`conversation_initiator/MVP_PLAN.md`](conversation_initiator/MVP_PLAN.md): the laptop MVP and its first results.
5. [`conversation_initiator/README.md`](conversation_initiator/README.md): what is in the package now, and how to run it.
6. [`readme.md`](readme.md): the project summary and the BWI workspace setup.

`docs/llm_decision_layer.docx` is a Word copy of the `.md` design doc.
The text of its first sections matches the `.md` file.

---

## 2. The architecture in short

The design doc (§2) describes a gated cascade:

1. Sensor nodes (audio, vision) measure the scene.
2. A fusion node merges them into one context JSON. It publishes on `/social_context` at 2 to 5 Hz.
3. A local gate with no LLM drops most ticks. It passes a tick only when a person is present and the scene changed. Target: suppress more than 90% of ticks.
4. The LLM scores a rubric, then picks an action. The call has a timeout of about 800 ms. On any failure, the robot stays silent.
5. If the action is `greet` or `respond`, a deterministic mapper turns the prosody enums into SSML. TTS then speaks it.

The LLM decides whether speech is appropriate. It does not time speech onset to the millisecond.

---

## 3. The frozen v1.0 schema contract

Files: `conversation_initiator/schema/`.

- `social_context.schema.json` is the input. It describes one decision moment.
- `decision.schema.json` is the output. It is the model's answer.
- `example.json` holds a full input, a matching decision, and a minimal input.

The input file is `social_context.schema.json`, not `context.schema.json`.

All payloads travel as JSON inside `std_msgs/String`. There is no custom `.msg` type.
`SCHEMA.md` §1 explains why.

### 3.1 Input: `/social_context`

Only two fields are required: `schema_version` (must be `"1.0"`) and `ambient.noise_db`.
All other fields are optional and have defaults.
If a node cannot measure a field, it must omit the field. It must not send a placeholder.
Every object sets `additionalProperties: false`, so the validator rejects unknown or misspelled keys.

| Block | Owner | Fields and meaning |
|---|---|---|
| top level | fusion / initiator | `t`: Unix time of the observation. `since_last_decision_s`: seconds since the last decision. |
| `ambient` | audio node | `noise_db` (required): A-weighted room level. `other_speech_active`: someone other than the robot talks. `noise_trend`: `rising`, `steady`, or `falling`. `speech_sources_estimated`: number of speakers. `reverberance`: `low`, `medium`, or `high`. |
| `target` | vision node | The one person the robot might address. `null` means nobody is present, and the gate then skips the LLM. Required if present: `distance_m`, `facing_robot`. Optional: `gaze_at_robot_s` (seconds of gaze), `motion` (`approaching`, `leaving`, `passing`, `stationary`), `in_conversation`, `activity` (`idle`, `working`, `socializing`, `transiting`, `unknown`), `bearing_deg`, `dwell_s` (seconds in view). |
| `target.speech` | audio node | `null` until the audio node sends transcripts. Fields: `detected`, `partial_transcript`, `syntactically_complete`, `prosody` (pitch, energy, words per minute), `tone_estimate`, `tone_confidence`. The `respond` action needs this block. |
| `bystanders[]` | vision node | Other people. Each has `distance_m` (required), `facing_robot`, `in_conversation`. An empty list means "looked, saw nobody." |
| `robot` | initiator only | `is_speaking`, `last_spoke_s_ago` (`null` means never), `last_utterance`, `consecutive_no_response` (times the robot was ignored). |
| `recent_decisions[]` | initiator only | Newest first. Each has `s_ago`, `action`, and optional `reason`. It stops the robot from repeating itself. |

There is no location or room field. This is a decision (`SCHEMA.md` §8).

### 3.2 Output: `/initiation_decision`

| Field | Meaning |
|---|---|
| `rubric` | Six integer scores from 1 to 5: `invitation`, `interruption_cost`, `urgency`, `redundancy`, `ambient_fit`, `addressivity`. |
| `action` | `remain_silent`, `wait`, `greet`, or `respond`. |
| `category` | `appropriate_to_initiate`, `inappropriate_to_interrupt`, `person_needs_assistance`, or `insufficient_evidence`. |
| `rule_fired` | The rule ID and a few words, for example `"R1 target in conversation"`. |
| `confidence` | A number from 0 to 1. It is poorly calibrated. Do not use it as a threshold. |
| `recheck_in_ms` | The cooldown the model asks for. The gate sets a minimum. |
| `speech` | `null`, or `text` with `volume`, `rate`, `pitch` enums and an optional `target_person_id`. The model never writes SSML. |

Do not reorder the properties.
Providers generate keys in schema order.
With `rubric` first, the model scores before it chooses an action.

### 3.3 How to change the schema

`SCHEMA.md` §7 has the rules:

- Add an optional field: no version bump.
- Remove, rename, retype, or make a field required: major bump, and the team must agree first.

Do not edit anything in `schema/` without a person's approval. See §6.

---

## 4. Current state

Today is September 22, 2026. Phase 0 is due today.

### 4.1 `conversation_initiator/` against the plan

Phase dates come from `IMPLEMENTATION_PLAN.md`.

| Phase | Dates | Plan | State in the repo |
|---|---|---|---|
| MVP | Sep 17 to 21 | `MVP_PLAN.md` steps 1 to 4 | Steps 1 and 4 done. `mvp.py` runs with Anthropic and Gemini on 8 vignettes. The gate (step 3) does not exist. There are 8 vignettes, not 20. |
| 0: skeleton | Sep 18 to 22 | ROS package, subscriber node, fake publisher, 20 vignettes, schema freeze | Schema frozen in the repo on Sep 18. No `package.xml`, no node, no fake publisher. The 8 vignettes use the old pre-v1.0 shape. Team sign-off is not recorded in the repo. |
| 1: providers | Sep 23 to Oct 1 | `schema.py` with three dialects, a provider interface, an OpenAI backend | Not started. `mvp.py` has two providers inline. |
| 2: latency | Oct 2 to 8 | Benchmark P50 and P95, pick one model | Not started. `MVP_PLAN.md` has free-tier numbers only. |
| 3: gate, safety | Oct 9 to 15 | Gate, timeout, post-filter, Langfuse, daily cap | Not started. |
| 4: live | Oct 16 to 22 | Real sensor nodes, `dry_run` on the robot | Not started. |
| 5: speech | Oct 23 to 29 | Prosody enums to SSML, Azure TTS | Not started. |
| 6: evaluation | Oct 30 to Nov 12 | 60 to 100 labeled vignettes, kappa, ablations | Not started. Scope is open (`SCHEMA_COMPARISON.md` §5). |

`.gitignore` already ignores `.env`. Item 4 in `IMPLEMENTATION_PLAN.md` §14 is done.

### 4.2 `audio_signals_FRI_II/`

A standalone Python 3.10 program. `python main.py` runs it.
It captures a microphone or a WAV file and runs Silero voice detection and loudness measurement.
Once per second it builds an `audio` JSON object with these fields: `stamp`, `noise_floor_db`, `noise_level`, `speech_snr_db`, `speech_now`, `speech_ratio_10s`, `seconds_since_speech`, `transcript`, `engaged`, `robot_speaking`.
Transcription uses local `faster-whisper`. It runs only while `engaged` is true.
All tunable numbers are in `audio_context/config.py`.
Its own `README.md` covers setup.
There is no ROS node. `main.py` and `state.py` refer to a future `node.py`.
Tone output is not written yet.

### 4.3 Homework packages

| Package | What it builds | State |
|---|---|---|
| `spatial_utils` | Library. `transformToMatrix`, `matrixToTransform`, `printTransform`. It converts between `TransformStamped` and 4x4 Eigen matrices. | Implemented. |
| `spatial_transforms` | `spatial_transform_node`: a GTK slider GUI that broadcasts `world` to `example_frame`. `tf_listener_node`: looks up that transform and broadcasts two offset frames. | Teaching demos. Implemented. |
| `nav_goals` | `send_goal`: sends one Nav2 `NavigateToPose` goal 1 m ahead of `base_link`, in the `map` frame. Forces `use_sim_time`. | Implemented. `examples.txt` has the TurtleBot4 simulator launch line. |
| `follower_robot` | Follows AprilTag ID 1 (tag25h9). It finds `tag1` in `base_link`, computes a goal `follow_distance` short of the tag, sends it to Nav2, and broadcasts a `go_to` frame. | Homework parts are filled in. |

Build: put the repo in `~/bwi_ros2/src` and run `colcon build` (see `readme.md`).
No build was run for this doc.

### 4.4 Work on other branches, not merged

| Branch | Content |
|---|---|
| `origin/swathi-vision-pipeline` | `hri_vision/`, an `ament_python` package. Kinect and webcam detection, orientation, and a person-context node that publishes on `/hri/vision/person_context`. |
| `origin/location-context`, `origin/decision-logic` | `location_context.py` matches the robot's pose to room rectangles. It outputs a `location` block with `room_label` and `room_type`. `decision-logic` adds a ROS node for it. |

Do not commit to these branches unless the owner asks you to.

---

## 5. Contradictions and open issues

Do not fix these without asking. Report them to a person.

### 5.1 Interface mismatches

1. **The audio output does not match `ambient`.** The audio node emits `noise_floor_db` in dBFS, which can be `null`. The schema needs `ambient.noise_db`, A-weighted and required. The audio README calls its output the `"audio"` block, but the schema has no `audio` key. `seconds_since_speech`, `speech_ratio_10s`, and `speech_snr_db` have no schema field.
2. **The vision branch does not match `target`.** It publishes `people[]` with `id`, `bbox`, `distance_m`, `direction`, and `dwell_time_s` on `/hri/vision/person_context`. The schema expects one `target` with `facing_robot`, `motion`, and more.
3. **No fusion node exists.** No plan names its owner. Something must turn the audio and vision outputs into `/social_context`.
4. **Location.** `SCHEMA.md` §8 says the schema has no location field and the robot stays at one fixed spot. The `location-context` and `decision-logic` branches build room labels. `audio_context/config.py` tells the user to measure "all three locations."
5. **`/speech_request` key.** `IMPLEMENTATION_PLAN.md` §2 uses `target_id`. `SCHEMA.md` and `decision.schema.json` use `target_person_id`.

### 5.2 Schema review notes, not yet decided

6. `bearing_deg` says "negative is left." ROS REP 103 treats counter-clockwise as positive, so left is positive. The schema names no reference frame.
7. `additionalProperties: false` conflicts with "add an optional field without a bump." A consumer on the old schema rejects a message with a new field.
8. No field gives a person an ID. `speech.target_person_id` refers to nothing in the input. `consecutive_no_response` counts "this person" but cannot tell people apart.

### 5.3 Docs against code

9. `SCHEMA.md` §5 says all 8 vignettes were migrated and validated. The vignette files are still in the old shape. No migration script is in the repo.
10. `mvp.py` does not use the v1.0 schema. Its `Decision` has 3 rubric scores, not 6. It has 3 actions, with no `respond`. It has no `category`, `recheck_in_ms`, or `speech`. Its input is the old `person` shape.
11. There are two rule sets. `mvp.py` has R1 to R6 in its system prompt. The design doc §5.2 has five example rules numbered 1 to 5, with different content. `rule_fired` examples use the `mvp.py` IDs.
12. The primary model differs. The design doc names Gemini 3.1 Flash-Lite. `IMPLEMENTATION_PLAN.md` names Claude Haiku 4.5. `mvp.py` defaults to Anthropic.
13. `IMPLEMENTATION_PLAN.md` §3 pins `anthropic>=0.40`. `mvp.py` needs `messages.parse`, and `mvp/requirements.txt` pins `anthropic>=0.125`.
14. `IMPLEMENTATION_PLAN.md` lists a Deepgram credit for the audio node. The audio node uses local `faster-whisper`.
15. `MVP_PLAN.md` says it supersedes `IMPLEMENTATION_PLAN.md` "for now." It also says phases 0 to 2 are "largely already done." The Phase 0 ROS code does not exist.

### 5.4 Code smells found while reading

These are notes only. Nothing was changed.

16. `follower_robot/package.xml` depends on `spatial_util`, which does not exist. The package is `spatial_utils`. It also omits `rclcpp_action`, `cv_bridge`, `geometry_msgs`, `sensor_msgs`, `tf2_ros`, and `eigen`, which `CMakeLists.txt` finds. `rosdep` may miss them.
17. `follower_robot` finds `cv_bridge`, `OpenCV`, and `sensor_msgs` but no source file uses them.
18. `FollowerRobotNode::computeAndAct` logs "Could not transform world -> example_frame." It looks up `map` and `tag1`.
19. `nav_goals/src/send_goal.cpp` has two wrong comments. "Move 2 meters forward" is next to `1.0`. "1 Hz retry loop" is next to `Rate(2.0)`.
20. `spatial_utils/include/spatial_utils/transform_util.h` has no include guard.
21. `spatial_transforms/CMakeLists.txt` exports an `include` directory that does not exist.
22. `SpatialTransformNode` does not initialize `x_`, `y_`, `z_`. It broadcasts them before anyone moves a slider.
23. Homework comments such as "You implement this" are still in the code, but the code is now implemented.
24. `audio_context/state.py` hard-codes `TAIL_SEC = 0.5`. `config.py` also has `robot_speaking_tail_sec`, and it says no other file holds a threshold.
25. `audio_signals_FRI_II/tools/test_capture.py` refers to `levels.py`, which does not exist.
26. Most `package.xml` files still have `TODO` descriptions and licenses.

---

## 6. Rules for agents

### 6.1 Git

- Make a new branch before you change anything.
- Do not commit to `main`.
- Do not commit to a branch that someone else may use, unless a person tells you to.
- Do not add `Co-Authored-By` lines. Do not add AI or assistant attribution or signatures anywhere. This includes commits, PR titles, PR bodies, and code.
- Keep commit messages short and plain. Say what changed, not why.
- Never commit `.env` files, API keys, or credentials.

### 6.2 Code comments

- Write a comment only where the code does not explain itself.
- Do not comment every line. Do not restate what the code or a name already says.
- If a function name and body are clear, write no comment.

### 6.3 Writing style

Write all comments, docstrings, and docs in Simplified Technical English:

- Use short sentences. Put one idea in each sentence.
- Use plain, common words.
- Use the active voice.
- Do not use idioms.

### 6.4 Keep docs current

- If your change affects this file or a doc it points to, update that doc in the same PR.
- Examples: a phase is finished, a package is added, a contradiction in §5 is fixed, or a rule changes.
- Update the "Last checked" line at the top when you check this file against the code.

### 6.5 Ask first

- Ask before you edit anything in `docs/`.
- Ask before you edit `conversation_initiator/SCHEMA.md`.
- Ask before you edit anything in `conversation_initiator/schema/`. It is frozen.
- These files hold decisions the team agreed on. An agent must not change them alone.

### 6.6 When something is unclear

- If something looks unfinished, contradictory, or ambiguous, say so and ask.
- Do not guess. Do not fix it silently.
- If two docs disagree, report both versions. Do not choose one as true.

---

## 7. Useful skills from `anthropics/skills`

Source: <https://github.com/anthropics/skills>, checked September 22, 2026.
Nothing is installed by this repo.
Ask a person before you install anything.

No skill in that repo covers ROS 2, C++, Nav2, robotics, or audio processing.

| Skill | Path | Why it helps here |
|---|---|---|
| `claude-api` | `skills/claude-api` | Claude API reference: model IDs, structured output, tool use. Use it for the provider code in `conversation_initiator/`. The skill skips itself when a project uses Gemini, so you may have to call it by name. |
| `doc-coauthoring` | `skills/doc-coauthoring` | A workflow to write design docs and decision docs. |
| `docx` | `skills/docx` | Read and edit `docs/llm_decision_layer.docx`. |
| `skill-creator` | `skills/skill-creator` | Write project skills. An example is a colcon build skill, which would fill the ROS gap. |
| `mcp-builder` | `skills/mcp-builder` | Build MCP servers in Python. Use it only if the team decides to expose robot functions to an LLM through MCP. |
| `pdf` | `skills/pdf` | Read papers or datasheets that come as PDF files. Rarely needed. |

Install in Claude Code (from the repo README):

```
/plugin marketplace add anthropics/skills
/plugin install example-skills@anthropic-agent-skills     # doc-coauthoring, skill-creator, mcp-builder
/plugin install document-skills@anthropic-agent-skills    # docx, pdf, pptx, xlsx
/plugin install claude-api@anthropic-agent-skills
```

License: `docx`, `pdf`, `pptx`, and `xlsx` are source-available and proprietary. Most other skills are Apache 2.0.
The README says the skills are for demonstration and education.

---

## 8. Quick commands

```bash
# LLM MVP (no ROS)
cd conversation_initiator/mvp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add GEMINI_API_KEY and/or ANTHROPIC_API_KEY
python3 mvp.py --provider anthropic

# Check that the example is valid against the schema
pip install jsonschema
python3 -c "import json; from jsonschema import Draft202012Validator as V; \
s=json.load(open('conversation_initiator/schema/social_context.schema.json')); \
V(s).validate(json.load(open('conversation_initiator/schema/example.json'))['social_context']); print('valid')"

# Audio subsystem (no ROS)
cd audio_signals_FRI_II
python tools/check_devices.py
python main.py --seconds 10

# ROS 2 C++ packages
cd ~/bwi_ros2 && colcon build && source install/setup.bash
ros2 run follower_robot follower_robot
```
