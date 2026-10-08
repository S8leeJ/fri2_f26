# What the audio numbers mean

This is a reference for whoever writes the LLM prompt.
It explains every field of the `/audio_context` JSON.

- Microphone: the 7-microphone array in the Azure Kinect, on flexo.
- Measured on October 8, 2026.
- A value marked "not measured yet" still needs a test. Part "How to measure" at the end says how.

Three fields depend on the microphone and its capture volume: `noise_floor_db`, `speech_snr_db`, and `tone.intensity_db`.
If the microphone or the volume changes, measure them again.

A real message from flexo:

```json
{"stamp": 1791447072.19993, "noise_floor_db": -58.9, "noise_level": "quiet", "speech_snr_db": 7.0, "speech_now": false, "speech_ratio_10s": 0.28, "seconds_since_speech": 1.3, "transcript": "Hello, what is the way to the library?", "tone": {"intensity_db": -53.1, "seconds": 3.79, "active_ratio": 1.0}, "engaged": true, "robot_speaking": false}
```

---

## `stamp`

The Unix time, in seconds, of the newest audio that the node measured.
It tells when the sound happened, not when the message was built.

- Use it to find the age of the audio data. If the current time minus `stamp` is more than about 2 seconds, the data is old.
- While `robot_speaking` is `true`, the node measures nothing. Then `stamp` is the time when the message was built.

## `noise_floor_db`

The level of the room when nobody talks, in dBFS.
0 dBFS is the loudest sound that the microphone can record, so the values are negative. A more negative value means a quieter room.
The node takes the median of the frames without speech in the last 10 seconds.

| Room | Value on the Kinect |
|---|---|
| Quiet room, nobody talks | about −59.5 dBFS |
| Moderate, people talk nearby | not measured yet |
| Loud, for example a busy hallway | not measured yet |

- `null` for the first 3 seconds after the node starts. It is also `null` for about 3 seconds after the robot talks for more than 10 seconds.
- dBFS is not a sound pressure level. In the prompt, use `noise_level` for the room.
- Use the number only to compare with `tone.intensity_db` in the same message.

## `noise_level`

One word for `noise_floor_db`: `quiet`, `moderate`, or `loud`.

| Label | Rule in `config.py` |
|---|---|
| `quiet` | below `quiet_max_db` (now −50 dBFS) |
| `moderate` | from `quiet_max_db` to `moderate_max_db` (now −40 dBFS) |
| `loud` | above `moderate_max_db` |

- A quiet room on the Kinect (−59.5 dBFS) gives `quiet`.
- The two cutoffs are placeholders until the moderate and loud rooms are measured.
- A 2 dB margin stops the label from switching back and forth at a cutoff.
- `null` when `noise_floor_db` is `null`.

## `speech_snr_db`

How far the voices rise above the room, in dB.
It is the median level of the speech in the last 10 seconds, minus `noise_floor_db`.
A larger value means a closer or louder voice.

| Value on the Kinect | Voice |
|---|---|
| about 5 | quiet voice |
| about 12 | loud voice, close to the robot |

A rough reading from these two measurements:

| Value | Reading |
|---|---|
| below 5 | faint or far away. Probably not talking to the robot. |
| 5 to 12 | normal speech, at a normal distance |
| above 12 | loud or close |

- The value covers the last 10 seconds. After speech stops, the value stays for up to 10 seconds.
- `null` when there was no speech in the last 10 seconds, or when `noise_floor_db` is `null`.

## `speech_now`

`true` while someone talks.

- The node smooths it. It becomes `true` after about 0.25 seconds of speech. It becomes `false` after 0.5 seconds of silence.
- A cough does not make it `true`. The short gaps between words do not make it `false`.
- It is late by about 0.25 to 0.5 seconds compared with the real speech.
- `null` while `robot_speaking` is `true`.

## `speech_ratio_10s`

The part of the last 10 seconds that had speech, from 0 to 1.
It comes from voice detection, so the microphone has little effect on it.
These bands come from the PlayStation Eye measurements:

| Value | Meaning |
|---|---|
| 0.00 | silence |
| 0.05 to 0.20 | one short remark, or someone who walks past |
| 0.20 to 0.35 | an exchange with pauses, or one long sentence |
| above 0.40 | a conversation in progress |

- A high value is the strongest sign that people are in a conversation. The robot should then stay out of it.
- One question to the robot changes this value only a little.
- `null` while `robot_speaking` is `true`.

## `seconds_since_speech`

The length of the current pause, in seconds. `0.0` while someone talks.

| Value | Meaning |
|---|---|
| under 1 | in the middle of a sentence or an exchange |
| 1 to 3 | the end of a turn. A good moment to reply. |
| over 5 | real silence |

- `null` means that nobody spoke since the node started. It does not mean a long pause.
- `null` while `robot_speaking` is `true`. After the robot talks, the value includes the time that the robot talked.

## `transcript`

The last finished utterance, as text.

- Only when `engaged` is `true`. Otherwise it is `""`.
- It appears about 1 second after the person stops talking.
- It stays until the next utterance is transcribed. It does not clear when the robot replies. So the same text can be in many messages.
- Do not treat a repeated transcript as a new question. Compare it with `seconds_since_speech` and with the conversation history.
- The speech model is small (`tiny.en`). It can mishear words, most often in short phrases. Treat the text as approximate.

## `tone`

How the last utterance sounded. The node measures it only while `engaged` is `true`.
`null` when nobody spoke while engaged.

| Field | Meaning |
|---|---|
| `intensity_db` | The level of the last utterance, in dBFS. On the Kinect: about −47 for a loud voice, about −54 for a quiet voice. |
| `seconds` | The length of the audio around the utterance. It includes about 1.3 seconds of audio before and after the speech, so it is longer than the speech itself. Compare it between utterances. Do not read it as the exact length. |
| `active_ratio` | The part of the utterance with energy within 30 dB of its peak. Near 1.0 for normal speech close to the robot. A low value means gaps or a far voice, so trust `tone` and `transcript` less. |

- Compare `intensity_db` with `noise_floor_db` in the same message. Do not use the raw number alone.
  In a quiet room (−59.5 dBFS), a loud voice is about 12.5 dB above the room, and a quiet voice is about 5.5 dB above it. These match the `speech_snr_db` values.
- A known bug: `tone` does not clear when `engaged` becomes `false`. So ignore `tone` when `engaged` is `false`.

## `engaged`

A copy of the `/engaged` input, which the decision layer sets.
`true` means that the robot is in a conversation, so transcription and `tone` are on.
It does not measure whether the person wants contact.

When `engaged` is `true`:

- Use `transcript`, `tone`, and `seconds_since_speech`. Together they show what the person said, how they said it, and if their turn ended.
- `transcript: ""` means that nobody finished a sentence since the robot engaged, or that transcription still runs.
- Avoid: treating a transcript that was already answered as a new question.

When `engaged` is `false`:

- `transcript` is always `""`, and `tone` is not updated.
- `""` does not mean that nobody spoke. It means that the node did not transcribe.
- Use `speech_now`, `speech_ratio_10s`, and `speech_snr_db` to see if people talk.
- Avoid: reading anything from `transcript` or `tone`.

## `robot_speaking`

A copy of the `/robot_speaking` input.
`true` means that the robot's own voice plays, and the microphone hears only the robot.

When `robot_speaking` is `true`:

- All measurements are `null`. `transcript` is `""`, and `tone` is `null`. `stamp` is the time when the message was built.
- `null` means "not measured". It does not mean silence.
- Avoid: making a decision from the audio fields. Avoid: reading `speech_now: null` as "nobody talks".

After `robot_speaking` becomes `false`:

- The node ignores audio for 0.5 seconds more, because the room still echoes the robot's voice.
- `noise_floor_db` and `speech_snr_db` can be `null` for about 3 seconds if the robot talked for more than 10 seconds.
- `seconds_since_speech` includes the time that the robot talked.

---

## What these numbers cannot tell

- Sound shows how activated a person is. It does not show if that is good or bad: a raised, loud voice can be happy or angry. The words show that, so use `transcript` and `tone` together.
- The node cannot tell who is talking. It cannot separate the target person from a bystander. There is no pitch, because the earlier pitch values were wrong on real speech (see `tone.py`).

## How to measure the missing values

Do these on flexo, with the Kinect microphone, at the place where the robot will stand.

1. **Noise floor for each room.** Nobody talks near the robot. Run this for 60 seconds, and write down the `floor` value:

   ```bash
   cd ~/fri2_f26/audio_signals_FRI_II && python3 main.py --show builder --seconds 60
   ```

   Do this in a quiet room, in a moderate room (people talk nearby), and in a loud room (a busy hallway).
2. **The `noise_level` cutoffs.** Put `quiet_max_db` halfway between the quiet and moderate floors. Put `moderate_max_db` halfway between the moderate and loud floors. Both are in `config.py`.
3. **`speech_snr_db` at distances.** In the quiet room, talk in a normal voice at 1 m, 2 m, and 4 m from the robot. Write down `snr` for each distance.

## The previous microphone

Before October 8, 2026, the node used a PlayStation Eye.
In the lab, its noise floor was −41 to −43 dBFS, and `speech_snr_db` was 10 to 15 at conversation distance.
These values do not apply to the Kinect.
