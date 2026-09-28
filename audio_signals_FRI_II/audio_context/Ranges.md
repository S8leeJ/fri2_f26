# What the audio numbers mean

Reference ranges for whoever writes the LLM prompt. Every figure here was
measured on this system, not assumed. Where a number depends on the
microphone, that is said plainly.

Measured on a PlayStation Eye four-microphone array at 16 kHz, in a room
whose noise floor sat at −41 to −43 dBFS.

---

## Transferable: these hold on any microphone

**`speech_snr_db`** — how far a voice rises above the room. A difference
between two levels, so the microphone and its gain cancel out.

| value | what it was |
|---|---|
| 3 to 5 | across the room, or spoken quietly |
| 6 to 9 | a few metres away, normal volume |
| 10 to 15 | conversational distance, speaking to the robot |
| above 15 | close, or raised |
| `null` | nobody has spoken recently |

The useful split for deciding whether someone is addressing the robot sits
around 8 to 10 dB. Below that they are probably talking to somebody else.

**`speech_ratio_10s`** — share of the last ten seconds with talking in it.

| value | what it was |
|---|---|
| 0.00 | silence |
| 0.05 to 0.20 | one remark, or someone passing |
| 0.20 to 0.35 | an exchange, turns with gaps |
| above 0.40 | a conversation already under way |

This is the field that separates two people talking to each other from one
person addressing the robot. A single question barely moves it.

**`seconds_since_speech`** — how long the room has been quiet. 0.0 while
someone is still talking, `null` if nobody has spoken at all. Under about a
second is mid-exchange; several seconds is a genuine pause.

**`tone.intensity_db` minus `noise_floor_db`** — the tone block's level is
only meaningful against the floor in the same object. The gap is what
carries the meaning. Across five readings of one phrase, said five ways:

| gap | delivery |
|---|---|
| +4 | quiet, as if not wanting to be overheard |
| +6 to +7 | normal |
| +11 | animated |
| +15 | irritated, clipped |

**`tone.seconds`** — how long the utterance took. Carries more than it
looks. The same phrase ran 4.1 s said animatedly and 2.1 s said irritably;
1.7 s quiet. Clipped and drawn out are both signals.

**`tone.active_ratio`** — share of the utterance with energy near its peak.
Near 1.0 at conversational distance, so it mostly reads 1.0 and carries
little. Worth watching only when it drops, which means a gappy or distant
utterance and therefore less to trust in the rest of the block.

---

## Not transferable: recalibrate on the robot

**`noise_floor_db`** is dBFS, relative to what the microphone can record.
It depends on the device and its gain, so a number from one setup means
nothing on another. Two readings taken so far:

| place | microphone | floor |
|---|---|---|
| library | laptop analog input | −59 dBFS |
| lab room | PlayStation Eye array | −41 to −43 dBFS |

Those differ by 17 dB for rooms that are not 17 dB apart. Most of that is
the microphone.

**Use `noise_level` instead.** It is the same measurement turned into
quiet, moderate or loud, using cutoffs that get set per installation. That
word survives a change of microphone; the number does not.

The cutoffs in `config.py` are still placeholders. Until the floor has been
read on the robot in the library, the hallway and the lab, `noise_level` is
a guess.

---

## Fields that need no explanation

`speech_now` is whether someone is talking at this moment, already smoothed
so it does not flicker between words. `transcript` is what was said, empty
unless engaged. `engaged` and `robot_speaking` are echoed from other nodes.

**While `robot_speaking` is true**, every measurement is `null`: the
microphone can only hear the robot, so nothing is being measured. `null`
across the board with `robot_speaking: true` means suppressed, not broken.

---

## What these cannot tell you

Acoustics predict how activated someone is. They do not predict whether
that is good or bad: raised pitch and volume look the same for delighted
and furious. Valence lives in the words, which is why `transcript` and
`tone` belong together in the prompt rather than either alone.

There is no pitch here. An earlier version tracked it and failed on real
speech in a room, reporting a voice near 110 Hz as 137 to 225. The fields
were removed rather than published wrong. See `tone.py` for the detail.