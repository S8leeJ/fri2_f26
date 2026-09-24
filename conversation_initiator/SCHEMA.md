# Context Schema v2.0

**Status:** v2.0, September 22, 2026. Supersedes the v1.0 freeze of September 18. Pending
sign-off from the audio and vision node owners; see §7 for what changed and why it is a
major version. This is the interface contract for `/social_context`.
**Machine-readable:** [`schema/social_context.schema.json`](schema/social_context.schema.json) · [`schema/decision.schema.json`](schema/decision.schema.json) · [`schema/example.json`](schema/example.json)
**Evidence behind the reconciliation:** [`SCHEMA_COMPARISON.md`](SCHEMA_COMPARISON.md)

This closes `IMPLEMENTATION_PLAN.md:184` (Phase 0 task 5) against the Sep 22 deadline at
`IMPLEMENTATION_PLAN.md:90`. It reconciles the two incompatible shapes that previously
existed — the design doc's schema (`docs/llm_decision_layer.md` §4/§6) and the MVP's
vignette shape — into one.

**If you own the audio or vision node, you only need §2 and §6.**

---

## 1. Topics

| Topic | Direction | Type | Rate | Payload |
|---|---|---|---|---|
| `/social_context` | fusion → initiator | `std_msgs/String` | 2–5 Hz | `social_context.schema.json` |
| `/initiation_decision` | initiator → logging | `std_msgs/String` | on decision | `decision.schema.json` |
| `/speech_request` | initiator → TTS | `std_msgs/String` | on greet/respond | the `speech` block, plus generated SSML |
| `/initiator_status` | initiator → * | `std_msgs/String` | 1 Hz | health, suppression rate, call count |

JSON-in-`String` rather than a custom `.msg`, per `IMPLEMENTATION_PLAN.md:103`: a custom
message forces every consumer to build against this package, and makes a schema change a
multi-package rebuild. It also means `ros2 topic pub` can inject test data by hand.

---

## 2. Input — `/social_context`

Only **two things are required**: `schema_version` and an `ambient` object, which may be
empty. Everything else has a documented default, so a node that can only produce part of
this is still a valid publisher. That is deliberate — it is what lets the initiator reach Phase 3 before
the sensor nodes exist.

### 2.1 Top level

| Field | Type | Required | Default | Owner |
|---|---|---|---|---|
| `schema_version` | `"2.0"` | **yes** | — | fusion |
| `t` | number/null | no | `null` | fusion |
| `since_last_decision_s` | number/null | no | `null` | initiator |
| `ambient` | object | **yes** | — | audio |
| `target` | object/null | no | `null` | vision |
| `bystanders` | array | no | `[]` | vision |
| `robot` | object | no | `{}` | initiator |
| `recent_decisions` | array | no | `[]` | initiator |

`target: null` means nobody is present. The gate keys off this and suppresses without
spending an LLM call.

### 2.2 `ambient` — audio node

Every field is optional. The first six are what the audio node in
`audio_signals_FRI_II` actually measures, under the names it already uses.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `noise_floor_db` | number ≤ 0 / null | `null` | room level with nobody talking, dBFS |
| `noise_level` | `quiet`\|`moderate`\|`loud`\|null | `null` | the audio node's label for the floor |
| `speech_snr_db` | number/null | `null` | how far a voice rises above the floor |
| `speech_now` | bool/null | `null` | someone is talking this second |
| `speech_ratio_10s` | 0–1 / null | `null` | share of the last 10 s with speech |
| `seconds_since_speech` | number ≥ 0 / null | `null` | current pause; `null` = nobody has spoken yet |
| `noise_db` | number | omitted | A-weighted level, calibrated microphone only |
| `other_speech_active` | bool | `false` | |
| `noise_trend` | `rising`\|`steady`\|`falling` | `"steady"` | |
| `speech_sources_estimated` | int/null | `null` | |
| `reverberance` | `low`\|`medium`\|`high`\|null | `null` | |

dBFS is relative to the microphone's full scale, so more negative is quieter, and the same
room reads differently on a different mic or gain. That is why it is not `noise_db`.
Publish `noise_db` only from a calibrated microphone, and never convert dBFS into it.

`null` means not measured, never zero. Three cases the model must not misread:
`seconds_since_speech: null` means nobody has spoken, not a long pause;
`speech_snr_db: null` means no voice, not a faint one; and while `robot.is_speaking` is
true every measured field is `null`, because the microphone only hears the robot.

### 2.3 `target` — vision node

| Field | Type | Required | Default |
|---|---|---|---|
| `distance_m` | number ≥ 0 | **yes** | — |
| `facing_robot` | bool | **yes** | — |
| `gaze_at_robot_s` | number ≥ 0 / null | no | `null` |
| `motion` | `approaching`\|`leaving`\|`passing`\|`stationary`\|null | no | `null` |
| `in_conversation` | bool | no | `false` |
| `activity` | `idle`\|`working`\|`socializing`\|`transiting`\|`unknown` | no | `"unknown"` |
| `bearing_deg` | number/null | no | `null` |
| `dwell_s` | number ≥ 0 / null | no | `null` |
| `speech` | object/null | no | `null` |

`target.speech` carries `detected`, `partial_transcript`, `syntactically_complete`,
`prosody{pitch_semitones_rel, energy_rel, rate_wpm}`, `tone_estimate`, `tone_confidence`.
All optional. **It is `null` until the audio node emits transcripts, and the `respond`
action is unreachable until it is populated** — without knowing what was said, the robot
can only initiate, never reply.

### 2.4 `bystanders[]`, `robot`, `recent_decisions[]`

`bystanders[]` — `distance_m` (required), `facing_robot`, `in_conversation`. An empty
list means nobody else is present, which is a different claim from the vision node being
unable to tell; use `[]` only when you actually looked.

`robot` — `is_speaking`, `engaged`, `last_spoke_s_ago`, `last_utterance`,
`consecutive_no_response`. Written by the initiator only. No sensor node writes these.
`engaged` means the robot is already in a conversation; the audio node reads it to decide
whether to transcribe, so an empty transcript while `engaged` is false is not silence.

`recent_decisions[]` — `s_ago` and `action` required, `reason` optional. Newest first.

---

## 3. Output — `/initiation_decision`

Design doc §6 adopted whole. Six rubric dimensions, four actions, four categories, plus
`category`, `recheck_in_ms`, and the nullable `speech` block.

**Property order is load-bearing.** Providers generate keys in schema order, so `rubric`
first forces the model to score all six dimensions before it picks an action — chain of
thought without a second call or a reasoning budget. Both prior schemas did this for the
same documented reason (`mvp.py:32`, `docs/llm_decision_layer.md:212`). Do not reorder.

| Field | Type | Notes |
|---|---|---|
| `rubric` | object, 6 × int 1–5 | `invitation`, `interruption_cost`, `urgency`, `redundancy`, `ambient_fit`, `addressivity` |
| `action` | enum | `remain_silent`, `wait`, `greet`, `respond` |
| `category` | enum | `appropriate_to_initiate`, `inappropriate_to_interrupt`, `person_needs_assistance`, `insufficient_evidence` |
| `rule_fired` | string | rule ID plus a few words |
| `confidence` | number 0–1 | see caveat below |
| `recheck_in_ms` | int ≥ 0 | model's own cooldown; the gate floors it |
| `speech` | object/null | enums only, never SSML |

`confidence` is bounded 0–1 here, which the design doc left unspecified. **It is
documented as poorly calibrated** — `MVP_PLAN.md:153` records values clustered 0.85–1.00
on every case, including one the model got wrong. Do not threshold on it without
validating against outcomes first.

`speech` carries `text`, `volume` (`x-soft`/`soft`/`medium`/`loud`), `rate`
(`slow`/`medium`/`fast`), `pitch` (`low`/`medium`/`high`), `target_person_id`. The model
emits **abstract enums only**; a deterministic mapper builds the SSML. A malformed SSML
tag fails silently at the speaker, whereas a bad enum fails loudly at the schema.

---

## 4. What changed, and why

Seven reconciliation calls. Each resolves a conflict catalogued in `SCHEMA_COMPARISON.md`.

**1. `target`, not `person`.** The design doc's name wins. Cosmetic, but the sensor nodes
build against this and the design doc is what they were specced from.

**2. Gaze is a duration, not a boolean.** `gaze_at_robot_s` over `gaze_on_robot`. A bool
is derivable as `gaze_at_robot_s > 0`; a duration is not recoverable from a bool. Take the
richer form and let consumers discard precision.

**3. Motion is a four-way enum, not `is_moving`.** This is the one change that fixes a
real defect. Vignettes `004` (walking past) and `006` (approaching) both set
`is_moving: true` and expect **opposite** actions — the bool cannot distinguish them.
Design doc rule 2 (`docs/llm_decision_layer.md:154`) keys specifically on `leaving` and
was unevaluable against MVP-shaped data.

**4. `in_conversation` lives on `target`, not only on bystanders.** R1 — the
highest-priority rule, "never greet someone already in a conversation" — is about the
person being addressed. The design doc only had this flag on `bystanders[]`, which left
the top-priority rule with nothing to read.

**5. `activity` is a closed vocabulary, not free text.** The MVP's string was carrying
three unrelated jobs: `talking_with_bystander_glancing_at_robot` encodes conversation
state, gaze, and motion in one unvalidated token. Those are now three structured fields,
and `activity` narrows to `idle`/`working`/`socializing`/`transiting`/`unknown` — enough
for R4 ("absorbed in work") and nothing more.

**6. One history mechanism, not two.** `robot.last_spoke_s_ago` is canonical;
`greeted_recently` is gone. "Recently" is a threshold the gate applies from `gate.yaml`,
not a fact a publisher should be baking in. One source of truth, tunable without a
schema change.

**7. `schema_version` added.** Neither prior shape had one. It is what makes this
freezable without being permanent — see §7.

### Added in v2.0

**8. `ambient` takes the audio node's real fields, and `noise_db` is no longer required.**
v1.0 was frozen on Sep 18; the audio node merged on Sep 19 and measures uncalibrated
dBFS, not an A-weighted level. Under v1.0 it could not publish at all without fabricating
`noise_db`, which the schema itself forbids. The six measured fields are added under the
audio node's own names, so no renaming layer sits between the two.

**9. `ambient_fit` redefined in the decision schema.** v1.0 read "1 = near-silent,
others working. 5 = active social noise", which scores a quiet library 1 and a room too
loud to hear the robot 5. That contradicts the rule prompt, and the schema description is
sent to the model alongside the prompt. It now reads "1 = inaudible or intrusive,
5 = well suited"; the cost of disturbing someone working belongs in `interruption_cost`.

**10. `robot.engaged` added.** The audio node already reads this flag to gate
transcription; the model needs it to tell "nobody spoke" from "not transcribing".

---

## 5. Migration

Both old shapes map mechanically. **All 8 existing vignettes were migrated and validated
against v1.0; all 8 pass.**

### From the MVP vignette shape

| Old | New |
|---|---|
| `person` | `target` |
| `person.gaze_at_robot_s` | `target.gaze_at_robot_s` *(unchanged)* |
| `person.is_moving` | `target.motion` — see mapping below |
| `person.in_conversation` | `target.in_conversation` *(unchanged)* |
| `person.activity` | split across `target.motion`, `target.in_conversation`, `target.activity` |
| `robot.greeted_recently` | `robot.last_spoke_s_ago` (bool → a number, or `null`) |
| `ambient.*` | unchanged |
| `robot.consecutive_no_response` | unchanged |

`activity` string → structured fields:

```
standing_idle                             -> motion=stationary,  activity=idle
seated_typing                             -> motion=stationary,  activity=working
walking_past                              -> motion=passing,     activity=transiting
walking_toward_robot                      -> motion=approaching, activity=transiting
approaching_robot                         -> motion=approaching, activity=transiting
talking_with_bystander                    -> motion=stationary,  activity=socializing
talking_with_bystander_glancing_at_robot  -> motion=stationary,  activity=socializing
```

The last two also imply a `bystanders[]` entry with `in_conversation: true`.

### From the audio node's output

`audio_context/audio_builder.py` publishes one flat object a second. Everything maps
by name except four fields:

| Audio node | Schema |
|---|---|
| `noise_floor_db`, `noise_level`, `speech_snr_db`, `speech_now`, `speech_ratio_10s`, `seconds_since_speech` | `ambient.*`, same names |
| `stamp` | `t` |
| `transcript` | `target.speech.partial_transcript` (empty string becomes `null`) |
| `robot_speaking` | `robot.is_speaking` |
| `engaged` | `robot.engaged` |

### From v1.0

Set `schema_version` to `"2.0"`. Nothing else is required: every v1.0 field still exists
with the same type, so a v1.0 context validates once the version string changes.

### From the design doc shape

Only three changes: `gaze_on_robot` → `gaze_at_robot_s`, `in_conversation` added to
`target`, and `activity` added as a closed enum. Everything else is as written in §4 of
the design doc.

**The vignette files themselves are unchanged in this PR.** Migrating them is mechanical
but touches the `expect` labels' provenance, so it belongs in its own change.

---

## 6. For the audio and vision node owners

The short version of what to publish. Everything not listed is optional and defaults
sensibly — send what you can actually measure, not what you wish you could.

**Audio node** — nothing is strictly required, but publish what `audio_builder.py`
already measures: `noise_floor_db`, `noise_level`, `speech_snr_db`, `speech_now`,
`speech_ratio_10s`, `seconds_since_speech`. Send `null` rather than a stale value while
the robot is speaking. Leave out `noise_db` unless the microphone is calibrated.
Everything else (`noise_trend`, `speech_sources_estimated`, `reverberance`, and the rest
of `target.speech`) can arrive later without a schema change.

**Vision node** — required if a person is present: `target.distance_m`,
`target.facing_robot`. Highest value next: `target.in_conversation` (drives the
top-priority rule) and `target.motion` (four-way — the bool version cannot distinguish
someone walking past from someone walking toward you). Then `gaze_at_robot_s`,
`bystanders[]`, `activity`, `bearing_deg`, `dwell_s`.

If you cannot produce a field, **omit it** — do not send a placeholder. An omitted field
reads as "not measured"; a fabricated one reads as fact.

---

## 7. Versioning

`schema_version` is `"2.0"` and is required. Consumers reject a major version they do not
recognise rather than guessing.

| Version | Date | Change |
|---|---|---|
| 1.0 | Sep 18 | First freeze |
| 2.0 | Sep 22 | `ambient.noise_db` no longer required; audio node fields and `robot.engaged` added; `ambient_fit` redefined (§4, changes 8–10). Major because a required field became optional and a rubric dimension changed meaning. |

- **Adding an optional field** — no version bump. This is why almost everything is
  optional.
- **Making a field required, removing one, renaming one, or changing a type or an enum's
  members** — major bump, and it needs the same team agreement this freeze got.

Frozen does not mean permanent. It means changes are visible, versioned, and agreed
rather than discovered at integration time.

---

## 8. Deliberately absent

**No location or room label.** Two independent reasons:

1. `docs/llm_decision_layer.md:80` makes it a stated design decision — send observable
   acoustic and social properties and let the model infer the setting, which addresses
   explicit guidance to avoid pre-defining environments for the robot.
   `IMPLEMENTATION_PLAN.md:30` lists localization as "nothing (deliberately — no room
   labels)."
2. The study runs the robot at a **single fixed spot**, so location is constant across
   every sample. It cannot inform a decision and cannot appear in an ablation, because
   there is no variance to remove.

Should the study later run in more than one setting, this section and
`SCHEMA_COMPARISON.md` §4 are the record of why the field was omitted and what a reversal
would cost.

---

## 9. Validating

```bash
pip install jsonschema
python - <<'EOF'
import json
from jsonschema import Draft202012Validator
s = json.load(open("conversation_initiator/schema/social_context.schema.json"))
d = json.load(open("conversation_initiator/schema/example.json"))["social_context"]
Draft202012Validator(s).validate(d)
print("valid")
EOF
```

Both schemas set `additionalProperties: false`, so an unknown or misspelled field is
rejected rather than silently dropped. That matters more than it sounds: a silently
dropped sensor field reads downstream as "the sensor saw nothing," which the model scores
as thin evidence and answers `remain_silent` to — a failure that is near-impossible to
spot in a log.

---

## 10. Still open

**Evaluation design** — `SCHEMA_COMPARISON.md` §5. The design doc §9 specifies an offline
vignette study with Fleiss' κ; the study as described is a live participant study at a
fixed spot. This does not block the schema freeze, but it decides whether the `speech`
block and a TTS path are on the critical path. Not resolved here.
