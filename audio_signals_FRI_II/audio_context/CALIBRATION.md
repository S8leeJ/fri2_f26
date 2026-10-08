# Audio calibration notes

These notes are for people. `Ranges.md` is the short version for the LLM system prompt.
When a measurement here changes, update `Ranges.md` too.
`Ranges.md` only describes what values mean. It never tells the LLM what to do, because the LLM weighs the audio with the other fields.

## Microphone

Since October 8, 2026, `config.py` uses the 7-microphone array in the Azure Kinect (`input_device: "Azure Kinect"`).
Three fields depend on the microphone and its capture volume: `noise_floor_db`, `speech_snr_db`, and `tone.intensity_db`.
If the microphone or the volume changes, measure them again.

## Measured on the Kinect

October 8, 2026, on flexo.

| Field | Condition | Value |
|---|---|---|
| `noise_floor_db` | quiet room, nobody talks | about −59.5 dBFS |
| `speech_snr_db` | quiet voice | about 5 dB |
| `speech_snr_db` | loud voice, close to the robot | about 12 dB |
| `tone.intensity_db` | quiet voice | about −54 dBFS |
| `tone.intensity_db` | loud voice | about −47 dBFS |

The values agree. In a quiet room, a loud voice is about 12.5 dB above the floor, and a quiet voice is about 5.5 dB above it.

The `speech_ratio_10s` bands in `Ranges.md` come from the PlayStation Eye. They come from voice detection, so the microphone has little effect on them.

## Not measured yet

- `noise_floor_db` in a moderate room (people talk nearby) and in a loud room (a busy hallway).
- So the `noise_level` cutoffs in `config.py` are still placeholders: `quiet_max_db` is −50, and `moderate_max_db` is −40. A 2 dB margin stops the label from switching back and forth at a cutoff.
- `speech_snr_db` at known distances.

## How to measure

Do these on flexo, with the Kinect microphone, at the place where the robot will stand.

1. **Noise floor for each room.** Nobody talks near the robot. Run this for 60 seconds, and write down the `floor` value:

   ```bash
   cd ~/fri2_f26/audio_signals_FRI_II && python3 main.py --show builder --seconds 60
   ```

   Do this in a quiet room, a moderate room, and a loud room.
2. **The `noise_level` cutoffs.** Put `quiet_max_db` halfway between the quiet and moderate floors. Put `moderate_max_db` halfway between the moderate and loud floors.
3. **`speech_snr_db` at distances.** In the quiet room, talk in a normal voice at 1 m, 2 m, and 4 m from the robot. Write down `snr` for each distance.

`tools/check_levels.py` says "Very low" for the Kinect, because speech peaks near −30 dBFS. Transcription still works. To raise the level, run `alsamixer -c 2`, press F4, and raise the capture control. Then measure everything again.

## How the fields behave

Details that `Ranges.md` leaves out:

- `noise_floor_db` is the median of the frames without speech in the last 10 seconds. It is `null` for the first 3 seconds, and for about 3 seconds after the robot talks for more than 10 seconds.
- `speech_snr_db` is the median level of the speech in the last 10 seconds, minus the floor. It needs at least 10 speech frames (about 0.3 seconds).
- `speech_now` becomes `true` after about 0.25 seconds of speech, and `false` after 0.5 seconds of silence.
- `tone.seconds` includes the 0.85 second margin before the speech and about 0.5 seconds after it.
- `transcript_age_s` counts from the end of the speech in the sentence. `seconds_since_speech` counts from the end of the 0.5 second silence check. So for the same sentence, `transcript_age_s` is about 0.5 seconds larger.
- `transcript_age_s` uses `stamp`, the time of the newest real audio. The node drops digital silence (exact zeros), so with a WAV file that ends in zeros, the age stops growing. A live microphone always sends real audio.
- `syntactically_complete` is `true` when the transcript ends in `.`, `?`, or `!`, and `false` when it ends in `...` or `…`, or has no end mark. It was tested on transcripts from October 2 and 8.
- The node ignores audio while `robot_speaking` is `true`, and for 0.5 seconds after.

## Known limits

- The transcript does not clear when the robot replies. `Ranges.md` says that the same text can be a sentence that was already answered. `transcript_age_s` shows how old it is.
- `tone` does not clear when `engaged` becomes `false`. `Ranges.md` says that `tone` can hold a value from an earlier conversation.
- The node cannot tell who is talking. The Kinect's 7 microphones could give the direction of a voice later.
- Sound shows how activated a person is, not if that is good or bad. The words show that.
- There is no pitch. The earlier pitch values were wrong on real speech (see `tone.py`).

## The previous microphone

Before October 8, 2026, the node used a PlayStation Eye.
In the lab, its noise floor was −41 to −43 dBFS, and `speech_snr_db` was 10 to 15 at conversation distance.
These values do not apply to the Kinect.
