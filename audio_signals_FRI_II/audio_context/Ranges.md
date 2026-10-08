# Audio fields

The robot's microphone gives these fields once each second.
Each field describes the audio. No single field decides what the robot does. Each one is evidence to weigh with the other fields.
`null` means "not measured". It never means zero or silence.
Levels are in dBFS. 0 dBFS is the loudest sound that the microphone can record, so the values are negative. A more negative value is quieter.

**`stamp`**: the Unix time, in seconds, of the newest audio. Audio data that is more than 2 seconds old can be out of date.

**`noise_level`**: `quiet`, `moderate`, or `loud`. A summary of `noise_floor_db`. It is more stable than the raw number. `quiet` is below about −58. `moderate` includes a room where people talk normally.

**`noise_floor_db`**: the room level between voices. A quiet room is about −59.5. A room where people talk normally is about −56. The number depends on the microphone, so it means most next to the voice levels in the same message.

**`speech_snr_db`**: how far voices rose above the room in the last 10 seconds, in dB.
- About 5: a quiet voice.
- About 12: a loud voice, close to the robot.
- Below 5: a faint voice, or a voice far from the robot.
- It stays for up to 10 seconds after speech stops. `null`: no speech in the last 10 seconds.

**`speech_now`**: someone talks now. It is about 0.5 seconds late. A cough does not count.

**`speech_ratio_10s`**: the part of the last 10 seconds that had speech, from 0 to 1.
- 0.05 to 0.2: one remark, or someone who walks past.
- 0.2 to 0.35: an exchange, or one long sentence.
- Above 0.4: a conversation in progress, or one person who talks for a long time.
- One question to the robot changes it only a little.

**`seconds_since_speech`**: the length of the current pause. 0 while someone talks.
- Under 1: usually the middle of a sentence.
- 1 to 3: usually the end of a turn.
- Over 5: silence.
- `null` means that nobody spoke yet. It does not mean a long pause.
- After the robot talks, it includes the time that the robot talked.

**`speech_bearing_deg`**: the direction of the voice in the last second, in degrees.
- 0 is straight ahead of the robot. Negative values are to the robot's left, and positive values are to its right. ±180 is behind.
- The field exists only when the robot uses the Kinect's microphone array. With another microphone, the message has no such field.
- `null` when nobody spoke in the last second.
- The average error is about 12 to 14 degrees for one speaker. When two people talk at the same time, the value can point to the louder one, or between them.

**`transcript`**: the last finished sentence, as text.
- It exists only while `engaged` is `true`.
- It stays until the next sentence. So the same text in several messages can be one sentence that the robot already answered.
- Words can be misheard.

**`transcript_age_s`**: the seconds since the person finished the sentence in `transcript`.
- A small value is a new sentence. The value grows while the same transcript stays.
- `null` when there is no transcript.

**`syntactically_complete`**: whether `transcript` ends like a finished sentence.
- `true`: it ends with a period, a question mark, or an exclamation mark.
- `false`: it ends without one, or with "...", which the speech model writes when speech trails off or is cut short.
- `null` when there is no transcript.
- It comes from the speech model's punctuation, so it can be wrong.

**`tone`**: how the last sentence sounded. It updates only while `engaged` is `true`.
- `intensity_db`: the level of the sentence. Its distance above `noise_floor_db` shows the voice level: about 12 dB above is a loud voice, about 5 dB above is a quiet voice.
- `seconds`: the length, plus about 1.3 seconds of extra audio. So it is longer than the speech itself.
- `active_ratio`: near 1.0 for normal speech. A lower value means gaps, or a far voice.

**`engaged`**: the robot is in a conversation.
- `true`: transcription is on. `transcript`, `tone`, and `seconds_since_speech` describe the person's last sentence. An empty transcript means that nobody finished a sentence yet.
- `false`: nothing is transcribed. An empty transcript does not mean silence. `speech_now`, `speech_ratio_10s`, and `speech_snr_db` still show if people talk. `tone` can still hold a value from an earlier conversation.

**`robot_speaking`**: the robot's own voice plays.
- `true`: the microphone hears only the robot. All measurements are `null`, which means not measured. In this message, the audio fields hold no information about people.
- The 0.5 seconds after it becomes `false` are also not measured.
