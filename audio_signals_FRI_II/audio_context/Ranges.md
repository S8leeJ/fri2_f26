# Audio fields

The robot's microphone gives these fields once each second.
`null` means "not measured". It never means zero or silence.
Levels are in dBFS. 0 dBFS is the loudest sound that the microphone can record, so the values are negative. A more negative value is quieter.

**`stamp`**: the Unix time, in seconds, of the newest audio. If it is more than 2 seconds old, the audio data is old.

**`noise_level`**: `quiet`, `moderate`, or `loud`. Use this word for the room.

**`noise_floor_db`**: the room level when nobody talks. A quiet room is about −59.5. Use it only to compare with voice levels.

**`speech_snr_db`**: how far voices rose above the room in the last 10 seconds, in dB.
- About 5: a quiet voice.
- About 12: a loud voice, close to the robot.
- Below 5: faint or far away. Probably not talking to the robot.
- It stays for up to 10 seconds after speech stops. `null`: no speech in the last 10 seconds.

**`speech_now`**: someone talks now. It is about 0.5 seconds late. A cough does not count.

**`speech_ratio_10s`**: the part of the last 10 seconds that had speech, from 0 to 1.
- 0.05 to 0.2: one remark, or someone who walks past.
- 0.2 to 0.35: an exchange, or one long sentence.
- Above 0.4: a conversation in progress. Do not interrupt it.
- One question to the robot changes it only a little.

**`seconds_since_speech`**: the length of the current pause. 0 while someone talks.
- Under 1: in the middle of a sentence.
- 1 to 3: the end of a turn. A good moment to reply.
- Over 5: silence.
- `null` means that nobody spoke yet. It does not mean a long pause.
- After the robot talks, it includes the time that the robot talked.

**`transcript`**: the last finished sentence, as text.
- It exists only while `engaged` is `true`.
- It stays until the next sentence, so it can repeat after the robot answered it. Do not treat a repeated transcript as a new question.
- Words can be misheard.

**`tone`**: how the last sentence sounded. Only while `engaged` is `true`.
- `intensity_db`: the level of the sentence. Compare it with `noise_floor_db`. About 12 dB above the floor is a loud voice. About 5 dB above is a quiet voice.
- `seconds`: the length, plus about 1.3 seconds of extra audio. Compare it between sentences.
- `active_ratio`: near 1.0 is normal speech. A lower value means gaps or a far voice.

**`engaged`**: the robot is in a conversation.
- `true`: use `transcript`, `tone`, and `seconds_since_speech`. An empty transcript means that nobody finished a sentence yet.
- `false`: nothing is transcribed. An empty transcript does not mean silence. Use `speech_now`, `speech_ratio_10s`, and `speech_snr_db` to see if people talk. Ignore `transcript` and `tone`.

**`robot_speaking`**: the robot's own voice plays.
- `true`: the microphone hears only the robot. All measurements are `null`, which means not measured. Do not decide from the audio fields.
- The 0.5 seconds after it becomes `false` are also not measured.
