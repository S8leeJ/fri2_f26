# playground

A local chat UI for the MVP. You type as the person in front of the robot.
Switches set the scene. Each reply shows what the robot decided, what it
said, and why.

Use it to probe the model one field at a time, to find new test cases, and
to demo the project. Hover over any control to see what it does. The
**? Help** button gives a short guide and the rules. It does not produce study results. In the
study, the participant decides what is right (`docs/llm_decision_layer.md` §9).

## How it works

```
 React app (localhost:5173)                 FastAPI server (127.0.0.1:8000)
 ┌──────────────────────────┐   POST       ┌──────────────────────────────┐
 │ Scene panel  -> context  │ ──/api/turn─► │ context.validate             │
 │ Chat box     -> speech   │               │ target null? -> no_person    │
 │                          │ ◄──result──── │ mvp.decide()  (call 1, 2)    │
 │ Robot bubble + diff      │               │ postfilter.enforce           │
 └──────────────────────────┘               └──────────────────────────────┘
```

The server imports the code in `../mvp`. It does not copy or change the
decision logic. The API keys stay in `../mvp/.env`. They never reach the
browser.

### One turn

1. **You build the scene.** The left panel edits one v2.0 context.
   - The scene list at the top groups the presets by the expected action.
   - Each card (Room, Person, Bystanders, Robot) shows a one-line summary.
     Click the title to fold it. The app remembers which cards are open.
   - A field you change from the preset turns orange. The card gets a dot
     and a **reset** button that loads the preset values for that card.
   - The **?** button on a choice means "not measured". The app then leaves
     the field out of the JSON.
   - The Conversation card lists what was said. **clear** empties it.
   - The Raw JSON card shows the exact object that goes to the server.
2. **You send a turn.**
   - **Send** puts your text in `target.speech.partial_transcript`. It also
     sets `robot.engaged` to true and `consecutive_no_response` to 0. The
     audio node only transcribes while engaged, and a reply means the person
     did not ignore the robot.
   - **Check scene** sends the scene with no speech. Use it to test whether
     the robot starts a conversation.
3. **The server decides.**
   - It validates the context against the schema. A bad field returns an
     error bubble, not a silent default.
   - If `target` is `null`, it returns `no_person` and makes no model call.
     The gate does the same on the robot.
   - Otherwise it runs `mvp.decide()` with the 6-score rubric. When the
     action is `greet` or `respond`, that makes a second call for the line.
     With `jev`, a greet uses a fixed line and makes no second call. Jev
     cannot write text, so a `respond` line comes from Groq, Gemini, or
     Anthropic, whichever has a key first.
   - It runs `postfilter.enforce()`. If the post-filter blocks the action,
     the server drops the line, because the robot would never say it.
4. **The app shows a robot bubble** with:
   - the line, or "(stays silent)" or "(waits)"
   - the final action, and the volume, rate and pitch
   - a red note if the post-filter blocked the model's action
   - the rule fired, the category, the confidence and `recheck_in_ms`
   - six rubric bars from 1 to 5
   - the provider, the model and the latency of each call
   - a **▶ play** button, if a TTS key is in `mvp/.env`. It shows whether
     the audio came from the cache or from the TTS engine.
5. **The app speaks the line** when the **voice** box in the header is on.
   The server sends the line to `mvp/tts.py` and returns a WAV file. The
   TTS key stays on the server.
   - "Changed since last turn": the fields you edited between turns
5. **The app writes history back** into the scene, as the initiator node
   would:
   - `recent_decisions` gets the new decision at the front. The app keeps 5.
   - `since_last_decision_s` goes to 0.
   - If the robot spoke: `last_utterance`, `last_spoke_s_ago` = 0, and
     `engaged` = true.
   - `conversation` gets your message when you send it, and the robot's line
     after it speaks. The app keeps the last 20. Both model calls see this
     list, so a reply such as "why?" follows the robot's previous line.
     Reset clears it.

### Buttons

| Button | Effect |
|---|---|
| +5 s, +30 s | Add time to `t`, `last_spoke_s_ago`, `since_last_decision_s`, each `recent_decisions[].s_ago` and each `conversation[].s_ago` |
| Ignored | Add 1 to `robot.consecutive_no_response` |
| Reset | Load the preset again and clear the chat |
| unfinished sentence | Send the next message with `syntactically_complete: false` |
| Save as vignette | Write the scene to `../mvp/vignettes/NNN_playground_<note>.json` with `expect: null` |

An empty number field or "(not measured)" removes the field from the
context. The schema says to omit a field that was not measured, so the app
does not send a placeholder. An empty `last_spoke_s_ago` sends `null`,
which means "never spoke".

## Setup

You need the MVP venv and Node 18 or later.

```bash
cd conversation_initiator/mvp
source .venv/bin/activate
pip install -r ../playground/requirements.txt

cd ../playground/web
npm install
```

The server uses the keys in `conversation_initiator/mvp/.env`. The provider
list only shows providers that have a key. Add `DEEPGRAM_API_KEY` to hear the
lines and to talk with the mic. Without it, the voice box, the play button,
and the **🎤 Talk** button do not appear.

### Talk instead of typing

Click **🎤 Talk**, speak, then click **■ Stop**. The browser records the
clip and sends it to `/api/listen`. Deepgram writes down what you said, and
the app sends the text as your message, the same as **Send**. With the voice
box on, the robot's answer is spoken back. The browser asks for mic access
the first time.

## Run

Terminal 1, the API:

```bash
cd conversation_initiator/playground
../mvp/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
```

Terminal 2, the web app:

```bash
cd conversation_initiator/playground/web
npm run dev
```

Open <http://localhost:5173>. The app opens on vignette 022, where the
person asks "Where is the elevator?".

## How to test

### Without a key

These tests do not call a model:

```bash
cd conversation_initiator/mvp
python3 test_gate.py          # also validates every vignette, including saved ones
python3 test_postfilter.py

cd ../playground/web
npm run typecheck
```

In the UI, clear **person present** and press **Check scene**. The bubble
must say "no model call (nobody present)".

### With a key

Use Groq. It is the fastest working provider. Do one check at a time.

| # | Steps | Expected result |
|---|---|---|
| 1 | Preset 022. Type "Where is the elevator?" and press Send. | `respond` with a line |
| 2 | Preset 024. Press Check scene. Then set `in_conversation` and press Check scene again. | First `greet`, then silent. If the model picks `greet`, the post-filter note says `R1 target in conversation`. |
| 3 | Preset 024. Set `noise_level` to quiet, Check scene. Set it to loud, Check scene. | Volume goes from `soft` to `loud`. The second bubble lists `ambient.noise_level: "quiet" -> "loud"`. |
| 4 | After the robot greets, press +5 s, then Check scene. Press +30 s, then Check scene. | Silent at 5 s (R2 cooldown). It may greet again after 35 s. |
| 5 | Clear person present. Press Check scene. | `remain_silent`, `no_person`, no model call |
| 6 | Press Save as vignette. Then run `python3 test_gate.py` in `mvp/`. | A new file with `expect: null`. The tests pass. |

Delete a test vignette when you are done with it, or keep it as a regression case.

### What to look for

- **One field at a time.** Change one switch per turn. Then the diff line
  names the cause of any change.
- **Repeat a turn.** Press Check scene twice with no change. If the action
  flips, the model is unstable on that scene. Save it as a vignette.
- **Lines that invent facts.** The robot has no map of the building. A reply
  with directions is wrong, even if it sounds helpful.
- **Wrong rule.** For example, R2 is about greetings. It must not block a
  reply to a question.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Cannot reach the server" | The API is not running. Start terminal 1. |
| `address already in use` on port 8000 | An old server still runs. Run `pkill -f "uvicorn server:app"`, then start it again. |
| A turn waits about 15 s | Groq's free tier allows about 4 turns a minute. The server waits and retries once after a 429. |
| Error bubble `502 ... 429` | The retry also hit the limit. Wait a minute, or pick another provider. |
| Error bubble `422 ...` | The context breaks the schema. The message names the field. Fix it in the raw JSON box. |
| "jev decides only" | Jev cannot write text. Pick Groq or Gemini to see lines. |
| The provider list is empty | `mvp/.env` has no keys. Add one and restart the server. |

## Files

| File | Purpose |
|---|---|
| `server.py` | FastAPI app. Endpoints: `/api/providers`, `/api/presets`, `/api/schema`, `/api/turn`, `/api/voice`, `/api/listen`, `/api/speak`, `/api/vignettes`. |
| `requirements.txt` | The MVP requirements plus FastAPI and uvicorn |
| `web/src/App.tsx` | Page layout, turn flow, provider picker, save |
| `web/src/ScenePanel.tsx` | Scene controls and the raw JSON box |
| `web/src/ChatPanel.tsx` | Chat log, robot bubbles, rubric bars, buttons |
| `web/src/MicButton.tsx` | Records a clip from the mic for `/api/listen` |
| `web/src/scene.ts` | Context helpers: set fields, diff, apply a result, move time |
| `web/src/api.ts` | Types and fetch calls for the server |
| `web/src/tips.ts` | The hover text for every control |
| `web/src/Tooltip.tsx` | Shows the hover text for any element with `data-tip` |
| `web/src/HelpModal.tsx` | The Help panel |
