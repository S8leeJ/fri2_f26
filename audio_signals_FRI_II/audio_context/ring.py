# Goal: keep the last few seconds of raw audio in memory, so a finished
# utterance can be pulled back out and transcribed.
#
#   ring = RingBuffer(CONFIG)
#   ring.add(block)                  # every block, always
#   ring.slice(span.start, span.end) # the samples for one utterance
#
# Always filling, even when not engaged. That is the point: when the LLM
# node decides to engage, the words spoken just before that decision are
# still here. Without the lookback the robot could only ever greet, never
# respond to someone who spoke first.
#
# In memory only. Nothing is written to disk, so the promise that raw audio
# is discarded after processing holds.

import threading

import numpy as np


class RingBuffer:

    def __init__(self, cfg):
        self.rate = cfg["sample_rate"]
        self.max_samples = round(cfg["ring_buffer_sec"] * self.rate)
        self._lock = threading.Lock()
        self._samples = np.zeros(0, dtype=np.float32)
        self._start_t = None       # timestamp of the oldest sample held
        self._next_t = None        # where the next block should start
        self.gaps = 0              # how often audio went missing

    def add(self, block):
        # One block from capture.py. Old audio falls off the front.
        with self._lock:
            if self._start_t is None:
                self._start_t = block.t
                self._next_t = block.t

            # The processor skips blocks while the robot is speaking, so the
            # audio arriving here is not always contiguous. Slicing works by
            # counting samples forward from _start_t, so a gap left unfilled
            # would put every later timestamp out by the missing duration,
            # and utterances would slice to the wrong audio or to nothing.
            # Filling it with silence keeps the timeline exact.
            gap = block.t - self._next_t
            if gap > 0.001:
                self.gaps += 1
                self._samples = np.concatenate([
                    self._samples,
                    np.zeros(round(gap * self.rate), dtype=np.float32)])

            self._samples = np.concatenate([self._samples, block.samples])
            self._next_t = block.t + len(block.samples) / self.rate

            excess = len(self._samples) - self.max_samples
            if excess > 0:
                self._samples = self._samples[excess:]
                self._start_t += excess / self.rate

    def slice(self, start_t, end_t):
        # The samples between two timestamps, or None if that stretch has
        # already aged out. Callers must handle None: an utterance longer
        # than the buffer, or a slow transcriber, can both lose the audio.
        with self._lock:
            if self._start_t is None or len(self._samples) == 0:
                return None

            begin = round((start_t - self._start_t) * self.rate)
            finish = round((end_t - self._start_t) * self.rate)
            if begin < 0 or finish <= begin:
                return None
            out = self._samples[begin:min(finish, len(self._samples))]
            # An empty slice means the stretch is not here after all. Say so
            # rather than handing back nothing-shaped audio.
            return out.copy() if len(out) else None

    def last(self, seconds):
        # The most recent stretch, for transcribing retroactively the moment
        # the robot engages.
        with self._lock:
            n = min(round(seconds * self.rate), len(self._samples))
            return self._samples[-n:].copy() if n else None

    def __len__(self):
        with self._lock:
            return len(self._samples)

    def span(self):
        with self._lock:
            return len(self._samples) / self.rate