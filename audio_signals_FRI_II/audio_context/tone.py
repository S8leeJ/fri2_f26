# Goal: measure how a voice sounded, rather than what it said. Produces the
# tone field.
#
#   tone = Tone(CONFIG)
#   tone.measure(samples)     # one finished utterance
#   tone.latest()             # {"intensity_db": -27.7, ...} or None
#
# Called from processor.py when an utterance closes and the robot is
# engaged, on the same audio slice the transcriber gets. Runs inline in a
# millisecond or so.
#
# Level and timing, not pitch. An earlier version tracked pitch by
# autocorrelation and matched Praat on clean recordings, then failed on real
# speech at 7 dB SNR in a room: it locked onto harmonics, reporting 137 to
# 225 Hz for a voice that sits near 110, and gave interquartile ranges up to
# 332 Hz, which is wider than a human voice can go. Doing it properly needs
# a cepstral or YIN method tested against real recordings, so the fields are
# left out rather than published wrong.
#
# What is here does separate deliveries. Across five readings of one phrase,
# intensity above the noise floor ordered them correctly: quiet +4.4,
# flat +6.4, normal +6.7, animated +10.9, irritated +15.1 dB. Duration
# separated them further, with animated drawn out to 4.1 s and irritated
# clipped to 2.1 s.
#
# Numbers, not an emotion label. A classifier would have to be trained on
# acted emotion recordings, which transfer poorly to someone mildly annoyed
# at a robot across a room. The LLM can reason about the numbers; it cannot
# check a label.

import threading

import numpy as np


class Tone:

    def __init__(self, cfg):
        self.rate = cfg["sample_rate"]
        self.enabled = cfg["tone_enabled"]

        self._lock = threading.Lock()
        self._latest = None
        self.done = 0

    def measure(self, samples):
        # One finished utterance in. Stores the result for the builder.
        if not self.enabled or samples is None or len(samples) < self.rate * 0.2:
            return None

        samples = np.asarray(samples, dtype=np.float64)
        rms = float(np.sqrt(np.mean(np.square(samples))))
        if rms < 1e-9:
            return None                  # digital silence, nothing to measure

        # How much of the utterance carried any energy, as a rough check on
        # whether there was a voice here at all. Low means mostly silence,
        # so the other numbers describe very little.
        frame = int(0.01 * self.rate)
        n = len(samples) // frame
        if n:
            frames = samples[:n * frame].reshape(n, frame)
            levels = 20.0 * np.log10(
                np.sqrt(np.mean(np.square(frames), axis=1)) + 1e-12)
            active = float(np.mean(levels > levels.max() - 30.0))
        else:
            active = 0.0

        result = {
            # How loud, in dBFS. Only meaningful against noise_floor_db in
            # the same object: the gap is what says whether a voice was
            # raised or lowered, never the absolute number.
            "intensity_db": round(20.0 * np.log10(rms + 1e-12), 1),

            # How long it took to say. Carries more than it looks: an
            # irritated delivery clips short, an animated one draws out.
            "seconds": round(len(samples) / self.rate, 2),

            # Share of the utterance with energy within 30 dB of its peak.
            # Near 1 is continuous speech; low means mostly gaps.
            "active_ratio": round(active, 2),
        }

        with self._lock:
            self._latest = result
            self.done += 1
        return result

    def latest(self):
        with self._lock:
            return self._latest

    def clear(self):
        # Called when the robot disengages, so an old reading does not
        # linger into the next interaction.
        with self._lock:
            self._latest = None