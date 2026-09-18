# Schema Comparison — design doc vs. MVP

**Status:** Resolved. This is the evidence behind **[`SCHEMA.md`](SCHEMA.md) v1.0**, which
is the frozen contract. Read that first; read this when you want to know *why* a
particular call was made, or to reopen one.
**Scope:** Analysis of the two pre-v1.0 shapes. Describes the state before the freeze.
**Prepared:** September 18, 2026

> The field-by-field comparison below deliberately makes no recommendation — it was
> written before the decision, to inform it. `SCHEMA.md` §4 records the seven calls that
> were ultimately made and the reasoning for each.

Two incompatible JSON schemas currently exist in this repo. Neither is frozen —
`IMPLEMENTATION_PLAN.md:184` still lists "Freeze the context schema and post it to the
team channel" as an open Phase 0 task, and `IMPLEMENTATION_PLAN.md:90` sets the deadline
for agreeing it with teammates at **Sep 22**: *"It is the only thing that has to be
settled early; everything else can change privately."*

This document lays both schemas out field by field so that decision can be made from
evidence rather than from memory.

- §4 records the **location / room labeling** question, which is now **closed**.
- §5 records an **evaluation design** question that is **open** and is not resolved here.

## Sources compared

| Label | Source | Lines |
|---|---|---|
| **DD** | `docs/llm_decision_layer.md` §4 — input schema | 82–120 |
| **DD** | `docs/llm_decision_layer.md` §6 — output schema | 167–206 |
| **MVP** | `conversation_initiator/mvp/vignettes/*.json` — all 8 files | — |
| **MVP** | `conversation_initiator/mvp/mvp.py` — `class Decision` | 31–39 |

---

## 0. Headline numbers

- **DD input schema defines 31 leaf fields. MVP vignettes use 10.**
- **Exactly 3 fields appear at an identical path in both:** `ambient.noise_db`,
  `ambient.other_speech_active`, `robot.consecutive_no_response`.
- 2 more share a name but sit under a different parent (`distance_m`, `facing_robot` —
  under `target` in DD, `person` in MVP).
- **21 DD fields have no MVP counterpart. 5 MVP fields have no DD counterpart.**
- All 10 MVP fields are populated in all 8 vignettes. There are no optional fields in
  practice, because there is no validation layer that would permit one.

---

## 1. Input schema — field by field

`—` means absent from that schema. Rows marked **[DIFF]** represent the same concept in
incompatible ways and are expanded in §1.3.

### 1.1 Full mapping

| Concept | DD (§4) | MVP (vignettes) | |
|---|---|---|---|
| Timestamp | `t` *(float, unix)* | — | |
| Time since last decision | `since_last_decision_s` *(float)* | — | |
| **Ambient** | | | |
| Noise level | `ambient.noise_db` *(float, 41.5)* | `ambient.noise_db` *(int, 34–71)* | **[DIFF]** type |
| Other speech present | `ambient.other_speech_active` *(bool)* | `ambient.other_speech_active` *(bool)* | identical |
| Noise direction | `ambient.noise_trend` *(enum)* | — | |
| Concurrent speaker count | `ambient.speech_sources_estimated` *(int)* | — | |
| Room acoustics | `ambient.reverberance` *(enum)* | — | |
| **The person** | | | |
| Container name | `target` | `person` | **[DIFF]** naming |
| Distance | `target.distance_m` *(float)* | `person.distance_m` *(float)* | same name, new parent |
| Facing the robot | `target.facing_robot` *(bool)* | `person.facing_robot` *(bool)* | same name, new parent |
| Bearing | `target.bearing_deg` *(float)* | — | |
| Gaze | `target.gaze_on_robot` *(bool)* | `person.gaze_at_robot_s` *(float, sec)* | **[DIFF]** name + type |
| Motion | `target.motion` *(4-way enum)* | `person.is_moving` *(bool)* | **[DIFF]** cardinality |
| Dwell time | `target.dwell_s` *(float)* | — | |
| In conversation | *(only on `bystanders[]`)* | `person.in_conversation` *(bool)* | **[DIFF]** placement |
| Activity | — | `person.activity` *(free string)* | **[DIFF]** see §1.3.5 |
| **Speech in** | | | |
| Speech detected | `target.speech.detected` *(bool)* | — | |
| Transcript | `target.speech.partial_transcript` *(str)* | — | |
| Turn completeness | `target.speech.syntactically_complete` *(bool)* | — | |
| Pitch | `target.speech.prosody.pitch_semitones_rel` | — | |
| Energy | `target.speech.prosody.energy_rel` | — | |
| Speaking rate | `target.speech.prosody.rate_wpm` | — | |
| Tone | `target.speech.tone_estimate` *(str)* | — | |
| Tone confidence | `target.speech.tone_confidence` *(float)* | — | |
| **Others present** | | | |
| Bystander list | `bystanders[]` *(array)* | — | **[DIFF]** see §1.3.5 |
| — distance | `bystanders[].distance_m` | — | |
| — facing | `bystanders[].facing_robot` | — | |
| — in conversation | `bystanders[].in_conversation` | — | |
| **Robot state** | | | |
| Currently speaking | `robot.is_speaking` *(bool)* | — | |
| Last utterance text | `robot.last_utterance` *(str/null)* | — | |
| Time since speaking | `robot.last_spoke_s_ago` *(float/null)* | — | **[DIFF]** see §1.3.6 |
| Greeted recently | — | `robot.greeted_recently` *(bool)* | **[DIFF]** see §1.3.6 |
| Times ignored | `robot.consecutive_no_response` *(int)* | `robot.consecutive_no_response` *(int)* | identical |
| **History** | | | |
| Decision log | `recent_decisions[]` *(array)* | — | **[DIFF]** see §1.3.6 |
| — age | `recent_decisions[].s_ago` | — | |
| — action taken | `recent_decisions[].action` | — | |
| — reason | `recent_decisions[].reason` | — | |
| **Location** | | | |
| Room label | — *(excluded)* | — | **closed, see §4** |

### 1.2 Present in one schema only

**In DD, absent from MVP (21):** `t`, `since_last_decision_s`, `ambient.noise_trend`,
`ambient.speech_sources_estimated`, `ambient.reverberance`, `target.bearing_deg`,
`target.dwell_s`, `target.speech.detected`, `target.speech.partial_transcript`,
`target.speech.syntactically_complete`, `target.speech.prosody.pitch_semitones_rel`,
`target.speech.prosody.energy_rel`, `target.speech.prosody.rate_wpm`,
`target.speech.tone_estimate`, `target.speech.tone_confidence`, `bystanders[].distance_m`,
`bystanders[].facing_robot`, `bystanders[].in_conversation`, `robot.is_speaking`,
`robot.last_utterance`, `robot.last_spoke_s_ago`, plus the three `recent_decisions[]`
subfields.

**In MVP, absent from DD (5):** `person.gaze_at_robot_s`, `person.is_moving`,
`person.in_conversation`, `person.activity`, `robot.greeted_recently`.

Three of those five are not new *concepts* — they are DD concepts expressed differently.
Only `person.activity` has no DD counterpart of any kind.

### 1.3 Same concept, different representation

**1.3.1 `target` vs `person`** — a rename of the container. Mechanical to migrate, but it
means no vignette validates against a DD-shaped model, or vice versa.

**1.3.2 Gaze: `gaze_on_robot` (bool) vs `gaze_at_robot_s` (float seconds)** — DD asks
*is the person looking at me*; MVP asks *for how long*. The MVP form is strictly richer
and a bool is derivable from it; the reverse is not. Observed MVP values: 0.0, 0.9, 1.1,
1.4, 1.8, 3.2. Neither document states the threshold at which a duration becomes `true`.

**1.3.3 Motion: `motion` (4-way enum) vs `is_moving` (bool)** — DD distinguishes
`approaching` / `leaving` / `passing` / `stationary`; MVP collapses these to one bit.
Vignettes `004_walking_past_not_facing` and `006_approaching_robot_directly` both set
`is_moving: true` and carry opposite expected actions (`remain_silent` vs `greet`), so
the distinction is currently carried entirely by other fields. **DD rule 2
(`docs/llm_decision_layer.md:154` — "whose `motion` is `leaving`") cannot be evaluated
against MVP-shaped data at all.**

**1.3.4 `in_conversation` placement** — MVP puts it on the person being considered. DD
puts it *only* on `bystanders[]` entries, with no equivalent on `target`. The vignettes
that exercise this (`002`, `008`) rely on the person-level flag, and the MVP's own R1
(`mvp.py:52`, "Never greet someone who is in a conversation with another person") is
written against it. DD's equivalent rule 1 (`docs/llm_decision_layer.md:153`) is phrased
around *"another person is speaking and the target is participating"* — a different
formulation reading different fields.

**1.3.5 `person.activity` as a compound field** — the largest structural divergence. The
MVP's free-text `activity` string carries semantics DD spreads across three separate
structures. All values observed across the 8 vignettes:

```
approaching_robot                          -> DD target.motion
seated_typing                              -> (no DD equivalent)
standing_idle                              -> DD target.motion
talking_with_bystander                     -> DD bystanders[].in_conversation
talking_with_bystander_glancing_at_robot   -> DD bystanders[] + target.gaze_on_robot
walking_past                               -> DD target.motion
walking_toward_robot                       -> DD target.motion
```

The field is unconstrained — no enum, no validation — and the fifth value encodes three
facts at once. Whether the model is reading `activity` or the structured fields is not
distinguishable from the current MVP results.

**1.3.6 Interaction history: overlapping mechanisms** — DD offers
`robot.last_spoke_s_ago` (float), `robot.last_utterance` (str), and `recent_decisions[]`
(array). MVP offers `robot.greeted_recently` (bool). These overlap, but neither side is
derivable from the other: the bool cannot reconstruct timing, and DD has no single field
answering "did I already greet this person" without interpreting the array. MVP's R2
(`mvp.py:53`) and DD's rule 3 both depend on this and read different fields.

---

## 2. Output schema — field by field

| Field | DD (§6) | MVP (`Decision`, mvp.py:31) | |
|---|---|---|---|
| Rubric container | `rubric` *(nested object)* | *(flat on `Decision`)* | **[DIFF]** nesting |
| — invitation | `rubric.invitation` *(int)* | `invitation` *(int, ge=1 le=5)* | both |
| — interruption_cost | `rubric.interruption_cost` *(int)* | `interruption_cost` *(int, ge=1 le=5)* | both |
| — ambient_fit | `rubric.ambient_fit` *(int)* | `ambient_fit` *(int, ge=1 le=5)* | both |
| — urgency | `rubric.urgency` *(int)* | — | DD only |
| — redundancy | `rubric.redundancy` *(int)* | — | DD only |
| — addressivity | `rubric.addressivity` *(int)* | — | DD only |
| Action | 4 values | 3 values | **[DIFF]** see §2.2 |
| Category | `category` *(4-value enum)* | — | DD only |
| Rule fired | `rule_fired` *(str)* | `rule_fired` *(str)* | identical |
| Confidence | `confidence` *(number, unbounded)* | `confidence` *(float, ge=0.0 le=1.0)* | **[DIFF]** DD states no bounds |
| Self-set cooldown | `recheck_in_ms` *(int)* | — | DD only |
| Speech block | `speech` *(nullable object)* | — | DD only |
| — text | `speech.text` *(str)* | — | |
| — volume | `speech.volume` *(4-value enum)* | — | |
| — rate | `speech.rate` *(3-value enum)* | — | |
| — pitch | `speech.pitch` *(3-value enum)* | — | |
| — target person | `speech.target_person_id` *(int/null)* | — | |

### 2.1 Rubric dimensions

DD specifies 6; MVP implements 3. The MVP's three are a strict subset with identical
names. The three DD-only dimensions have never been exercised — and note that `urgency`
and `addressivity` are referenced by DD rules 2 and 5
(`docs/llm_decision_layer.md:154,157`), which therefore cannot currently be evaluated
either.

DD nests all six under a `rubric` object; MVP places its three directly on `Decision`.

### 2.2 Action enum

DD: `remain_silent`, `wait`, `greet`, `respond`.
MVP: `remain_silent`, `wait`, `greet`.

`respond` — reply to something said *to* the robot, as distinct from initiating — exists
only in DD. No vignette expects it, and the MVP has no input field carrying what was
said, since `target.speech.partial_transcript` is DD-only. **These two gaps are linked:
neither can be closed alone.**

### 2.3 Where the two agree

Both schemas deliberately place the scoring fields **first**, for the same documented
reason.

> "Field order matters: the rubric is scored before the action is chosen."
> — `mvp.py:32`

> "Gemini generates keys in **schema order**, so placing `rubric` first forces the model
> to score before deciding — effectively free chain-of-thought without a separate
> reasoning pass."
> — `docs/llm_decision_layer.md:212`

Any merged schema that preserves nothing else should preserve this.

---

## 3. Compatibility summary

| | Count |
|---|---|
| DD input leaf fields | 31 |
| MVP input leaf fields | 10 |
| Identical path and meaning | 3 |
| Same name, different parent | 2 |
| Same concept, incompatible representation | 6 |
| DD-only | 21 |
| MVP-only, genuinely new concept | 1 |

Neither input schema is a subset of the other. On the **output** side, the MVP **is** a
strict subset of DD.

---

## 4. CLOSED — location / room labeling

**Resolved Sep 18, 2026 by the component owner: no location field. Recorded here because
the sources disagreed, and the team may otherwise re-litigate it.**

Two sources in this repo excluded location on design grounds:

> **Key design decision:** do **not** send a room label. Send observable acoustic and
> social properties and let the model infer the setting. This directly addresses the
> guidance to avoid pre-defining environments for the robot.
>
> — `docs/llm_decision_layer.md:80`

> | Localization | Existing BWI stack | nothing (deliberately — no room labels) |
>
> — `IMPLEMENTATION_PLAN.md:30`

The project proposal was reported to treat location as one of three explicit context
sources, alongside audio and vision, which appeared to contradict the above. That
proposal is **not present in this repository**, so only one side of it is visible here.

**The contradiction dissolved rather than being adjudicated.** The study places the robot
at a **single fixed spot**. Location is therefore constant across every sample in the
dataset, which means:

1. It carries no information that could change a decision.
2. It cannot appear in an ablation, since there is no variance to remove.
3. The design doc's argument and the proposal's framing were answering different
   questions, not disagreeing about the same one.

**Neither schema gains a location field.** Should the study later run the robot in more
than one setting, this section is the record of why the field was omitted and what would
have to change.

---

## 5. OPEN — evaluation design

**Not resolved here. Flagged because it determines what the vignettes are for, and
therefore how much the schema decision actually matters.**

`docs/llm_decision_layer.md` §9 specifies an **offline** evaluation:

> Perform this **offline on frozen JSON vignettes**, not on the live robot. It is roughly
> two orders of magnitude cheaper and is the only route to real statistics.

That section's apparatus — 60–100 vignettes, three or more human labelers, Fleiss' κ as
the human-agreement ceiling, adjudicated reference labels, Spearman's ρ on the ordinal
rubric scores — is built for offline annotation by people who were never in the room.

The study as currently described is **live**: a participant interacts with the robot at
its fixed spot and afterwards judges whether the interaction was appropriate. That is a
different measurement — a judgment from inside the interaction, not an agreement score
from outside it. Both are legitimate and are commonly run together, but they need
different infrastructure and produce different claims.

The open question is which is the headline result:

| If | Then |
|---|---|
| **Both** — vignettes as the offline dev loop, live study as the paper result | Vignettes stay as a regression suite. Additionally needs per-interaction logging keyed to participant ID and their rating. Whether the κ machinery still earns its place on the vignettes becomes a separate call. |
| **Live only** | The 60–100 vignette target and the κ / adjudication apparatus in §9 come out of the design doc. ~20 vignettes suffice as dev fixtures. Materially less work. |

Note this interacts with the schema decision: a live study requires the robot to actually
speak, which requires the DD-only `speech` block (§2 above) and a TTS path. An offline
vignette study does not.

---

## 6. Other facts surfaced, no action implied

- **Neither schema is frozen.** `IMPLEMENTATION_PLAN.md:184`, Phase 0 task 5, is open,
  against a Sep 22 deadline at `IMPLEMENTATION_PLAN.md:90`.
- **The evidence base is thin in a specific way.** 21 of DD's 31 input fields are
  exercised by zero vignettes. That says nothing about whether they are needed — only
  that the current 8 vignettes cannot show it either way.
- **MVP has no validation layer.** Vignettes are consumed by `json.loads` with no schema
  check (`mvp.py:74`), so a renamed or missing field passes silently into the prompt.
- **`confidence` is documented as poorly calibrated.** `MVP_PLAN.md:153` records values
  clustered 0.85–1.00 on every case, including the one the model got wrong. Relevant to
  any merged schema that keeps the field.
- **Vignette `003` is a documented open disagreement, not an error.** `MVP_PLAN.md:145`
  records the owner's view that their own `expect` label was the weaker call, left in
  place deliberately.
- **The robot being at a fixed spot** means the Nav2 / AprilTag-follower packages
  (`follower_robot`, `nav_goals`, `spatial_transforms`, `spatial_utils`) are not part of
  this study's robot behavior. `readme.md` already frames them as a separate homework
  stack.
