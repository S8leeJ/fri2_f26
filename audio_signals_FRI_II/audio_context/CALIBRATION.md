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
| `noise_floor_db` | room where people talk normally | about −56 dBFS |
| `speech_snr_db` | quiet voice | about 5 dB |
| `speech_snr_db` | loud voice, close to the robot | about 12 dB |
| `tone.intensity_db` | quiet voice | about −54 dBFS |
| `tone.intensity_db` | loud voice | about −47 dBFS |

The values agree. In a quiet room, a loud voice is about 12.5 dB above the floor, and a quiet voice is about 5.5 dB above it.

The `speech_ratio_10s` bands in `Ranges.md` come from the PlayStation Eye. They come from voice detection, so the microphone has little effect on them.

## The `noise_level` cutoffs

- `quiet_max_db` is −58, halfway between the quiet room (−59.5) and the room where people talk normally (−56).
- `level_hysteresis_db` is 1 dB. The label changes from `quiet` to `moderate` at −57, and back to `quiet` below −59. The two rooms are only 3.5 dB apart, so a larger margin would keep the label stuck.
- `moderate_max_db` is −40. It is still a placeholder.

## Voice detection

On October 8, 2026, background noise read as speech. `speech_now` became `true` when nobody was near the robot, and `speech_ratio_10s` was about 0.5.

The cause: the detector scales each block to −25 dBFS before it scores it. A quiet room on the Kinect is near −59 dBFS, so its noise was raised about 34 dB, to the level of speech.

The fix, in `config.py`:

- `vad_max_gain_db` is 25. Scaling raises a block by 25 dB at most.
- `vad_threshold` is 0.45. It was 0.35.

In a simulation with the test clip at the Kinect levels, and five kinds of fan and hum noise at −56 dBFS:

| Setting | `speech_now` on noise | Voice frames found, loud voice | Voice frames found, quiet voice |
|---|---|---|---|
| Old: no limit, 0.35 | up to 0.56 of the time | 96% | 75% |
| New: 25 dB, 0.45 | 0 | 88% | 65% |

Check it on flexo. Run `python3 main.py --show builder --seconds 60` in `~/fri2_f26/audio_signals_FRI_II`, and do not talk for 30 seconds. Then talk at 1 to 2 m.

- Noise still reads as speech: set `vad_threshold` to 0.5, or `vad_max_gain_db` to 20.
- A quiet voice is missed: set `vad_threshold` to 0.4.

## Not measured yet

- `noise_floor_db` in a loud room (a busy hallway).
- `speech_snr_db` at known distances.
- The new voice detection settings on flexo.

## How to measure

Do these on flexo, with the Kinect microphone, at the place where the robot will stand.

1. **Noise floor for each room.** Nobody talks near the robot. Run this for 60 seconds, and write down the `floor` value:

   ```bash
   cd ~/fri2_f26/audio_signals_FRI_II && python3 main.py --show builder --seconds 60
   ```

   The quiet room and the room where people talk are done. Do this in a loud room.
2. **The `noise_level` cutoffs.** Put `moderate_max_db` halfway between the moderate floor (−56) and the loud floor. Keep `level_hysteresis_db` smaller than half the distance between two floors.
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

## Voice direction (`speech_bearing_deg`)

`audio_context/bearing.py` estimates the direction of a voice with SRP-PHAT.
It runs only when the capture device name contains `Azure Kinect` and the device has 7 channels, and `bearing_enabled` is `True` in `config.py`.
The audio log then shows `speech_bearing_deg on: ...`. With any other microphone, the JSON has no `speech_bearing_deg` field.

- Microphone positions come from `param/azure_kinect.yaml` in ssloc_ros (Universität Hamburg, MIT/Apache-2.0). Channel 0 is the centre. Channels 1 to 6 are a hexagon of 40 mm radius.
- It uses 300 Hz to 4 kHz, a 5° grid, and the voiced blocks of the last second (`bearing_window_sec`). Louder blocks and sharper peaks count more.
- In a simulation without echoes (the test clip, from 24 directions), the average error was 3.5° at 10 dB SNR and 4.9° at 5 dB SNR.
- On a real Azure Kinect, a 2023 thesis with the same method (Fredenhagen, Universität Hamburg) measured about 12° to 14° average error for one speaker. A second speaker at the same time gave unreliable results.
- The convention follows `bearing_deg` in the schema: negative is left. ROS REP 103 uses the opposite sign (see `AGENTS.md` §5.2).

### Calibrate the direction

The rotation of the microphone hexagon relative to the camera is not known, so calibrate once. Do it on flexo, at the place where the robot will stand.

1. In `audio_context/config.py`, set `bearing_offset_deg` to `0.0` and `bearing_mirror` to `False`.
2. Stop the audio node. Then run `python3 main.py --show json --engaged` in `~/fri2_f26/audio_signals_FRI_II`.
3. Stand about 1.5 m straight in front of the camera, and talk for 5 seconds. Write down `speech_bearing_deg` as F.
4. Stand about 1.5 m to the robot's left, and talk for 5 seconds. Write down `speech_bearing_deg` as L.
5. Compute L − F, and bring it into the range −180 to 180. If it is near −90, keep `bearing_mirror` at `False`. If it is near +90, set `bearing_mirror` to `True`, and change the sign of F.
6. Set `bearing_offset_deg` to −F.
7. Check: in front reads about 0, left about −90, right about +90, and behind about ±180.
8. Write down the two values here, and commit them on a branch.

Not calibrated yet.

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
