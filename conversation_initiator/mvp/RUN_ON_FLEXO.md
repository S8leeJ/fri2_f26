# Set up the LLM code on flexo

Use the robot **flexo** (IP `10.0.0.144`).
This guide installs the Python packages for `conversation_initiator/mvp/`, adds the API keys, and checks that text to speech plays on flexo's speakers.
It takes about 5 minutes.

Not tested on flexo yet. Written October 8, 2026.

## When to do what

| When | Do this |
|---|---|
| The first time, for each account | Steps 1 to 6 |
| Every time you start the robot | Nothing from this guide |
| A `git pull` changes `requirements.txt` | Steps 3 and 4 again |
| The robot is silent when it should talk | Step 6 again |
| You log in with a different account | Steps 1 to 6 |

The packages stay in `~/.local`.
The `.env` file stays in this folder. `git pull` does not change it, because git ignores `.env`.

## Before you start

- Get the keys from a teammate:
  - `DEEPGRAM_API_KEY`, for text to speech.
  - One LLM key: `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, or `TYPESAFE_API_KEY` (Jev).
- Do not commit the keys, and do not paste them into a chat.
- Open one Terminator pane. ROS does not need to be loaded.
- The audio and vision programs can keep running while you do these steps.

## 1. Get the newest code

```bash
cd ~/fri2_f26 && git switch main && git pull
```

- Expected: `Already up to date`, or a list of changed files.

## 2. Save a list of your packages

```bash
python3 -m pip freeze --user > ~/before_llm.txt
```

- Expected: no output.
- If something breaks later, `~/before_llm.txt` shows the versions that you had before.

## 3. Install the packages

```bash
cd ~/fri2_f26/conversation_initiator/mvp && python3 -m pip install --user -r requirements.txt -c <(printf 'numpy<2\nsetuptools==58.2.0\nmediapipe==0.10.14\nopencv-python==4.11.0.86\nopencv-contrib-python==4.11.0.86\nprotobuf<5\n')
```

- Expected: the output ends with `Successfully installed anthropic-... google-genai-... pydantic-2...`, or `Requirement already satisfied`.
- The `-c` part locks the versions that audio and vision need. If a new package needs a different version, pip stops with an error and changes nothing.
- The packages in `requirements.txt` do not use NumPy, OpenCV, MediaPipe, or setuptools.

## 4. Check the packages

```bash
python3 -c "import numpy, cv2, mediapipe, anthropic, google.genai, pydantic, jsonschema, dotenv; print('numpy', numpy.__version__, '| cv2', cv2.__version__, '| pydantic', pydantic.__version__, '| ✅ all load')"
```

- Expected: `numpy 1.26.4 | cv2 4.11.0 | pydantic 2.x | ✅ all load`

## 5. Add the keys

Make the file, and let only your account read it:

```bash
cp ~/fri2_f26/conversation_initiator/mvp/.env.example ~/fri2_f26/conversation_initiator/mvp/.env && chmod 600 ~/fri2_f26/conversation_initiator/mvp/.env
```

Open it:

```bash
nano ~/fri2_f26/conversation_initiator/mvp/.env
```

- Put your keys after the `=` signs for `DEEPGRAM_API_KEY` and your LLM key.
- Leave the other lines empty.
- Press **Ctrl+O** and **Enter** to save. Press **Ctrl+X** to close.
- `git status` must not show `.env`.

## 6. Test the speakers

```bash
cd ~/fri2_f26/conversation_initiator/mvp && python3 tts.py "Hello, I am flexo"
```

- Expected: a line that starts with `deepgram`, and you hear the sentence from flexo's speakers.
- The second time, the line says `cached`. The sound comes from `tts_cache/`, with no network call.

## Problems and fixes

| You see | Do this |
|---|---|
| A yellow `dependency resolver` warning in step 3 | Not a problem. Check step 4. |
| `Cannot install ... conflicting dependencies` in step 3 | Nothing changed. Send the output to the team. |
| `DEEPGRAM_API_KEY not set in .env.` | The key line is empty or has a typo. Do step 5 again. |
| No sound in step 6 | Run `aplay -l` to list the outputs. Set the output and the volume in Ubuntu's sound settings. The Kinect has only microphones, so it is not the output. |
