# Goal: turn a finished utterance into text, without ever holding up the
# rest of the pipeline. Produces the transcript field.
#
#   stt = Transcriber(CONFIG)
#   stt.request(samples)      # hand it an utterance, returns immediately
#   stt.latest()              # the most recent text, or ""
#
# On its own thread for a reason. Transcription takes a moment, and the
# per-second numbers have to keep flowing while it runs. The builder reads
# whatever text is ready and does not wait.
#
# Only runs when engaged. Most of the time nobody is talking to the robot,
# so this costs nothing, and bystanders who never agreed to anything do not
# get transcribed.

import io
import os
import queue
import threading
import time
import wave

import numpy as np

GROQ_URL = "https://api.groq.com/openai/v1"

_model = None


def _get_model(cfg):
    # Loaded once. Keep it on the CPU even on a machine with a GPU, or
    # timings here will not match the robot.
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(
            cfg["stt_model"],
            device=cfg["stt_device"],
            compute_type=cfg["stt_compute_type"],
            cpu_threads=cfg["stt_threads"],
        )
    return _model


def _wav(samples, rate):
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class Transcriber:

    def __init__(self, cfg, verbose=False):
        self.cfg = cfg
        self.rate = cfg["sample_rate"]
        self.verbose = verbose
        self.log_timing = False    # one line per transcript, without the words
        self.on_text = None        # called with no arguments when new text is ready
        self._groq = None          # an HTTP client when Groq transcribes
        self._groq_note = None     # why Groq is off, when stt_provider asks for it
        key = os.environ.get("GROQ_API_KEY")
        if cfg.get("stt_provider") == "groq":
            if not key:
                self._groq_note = "GROQ_API_KEY is not set"
            else:
                try:
                    import httpx
                    self._groq = httpx.Client(
                        base_url=GROQ_URL, headers={"Authorization": "Bearer " + key},
                        timeout=cfg.get("stt_groq_timeout_sec", 2.5),
                        limits=httpx.Limits(keepalive_expiry=60.0))
                except ImportError:
                    self._groq_note = "httpx is not installed"

        # Depth one: if a request is already waiting, a newer utterance
        # replaces it. Falling behind is better than queueing up stale audio
        # and reporting a transcript from a minute ago.
        self._queue = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._text = ""
        self._text_t = None        # when the transcribed audio happened
        self._trace = None         # wall times for the latest transcript
        self._stop = threading.Event()
        self._thread = None
        self.done = 0              # utterances transcribed
        self.skipped = 0           # requests dropped because one was in flight
        self.available = None      # set by warm_up: False if the model failed

    def start(self):
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def warm_up(self):
        # Load the model before the first real utterance, so the first
        # transcript is not delayed by a one-off setup cost.
        #
        # Never fatal. Transcription is one optional field; if the model
        # cannot be fetched, the node should carry on measuring the room
        # rather than refusing to start. Returns whether it is usable.
        try:
            _get_model(self.cfg)
            self.available = True
        except Exception as e:
            self.available = False
            print(f"transcription unavailable, carrying on without it: "
                  f"{type(e).__name__}")
        if self._groq is not None:
            try:
                self._groq.get("/models")   # opens the connection before the first sentence
            except Exception:
                pass
            print(f"transcription: Groq {self.cfg.get('stt_groq_model')}, "
                  f"local {self.cfg['stt_model']} if Groq fails", flush=True)
        elif self._groq_note:
            print(f"transcription: local {self.cfg['stt_model']}, because {self._groq_note}",
                  flush=True)
        return self.available

    def _ask_groq(self, samples):
        response = self._groq.post(
            "/audio/transcriptions",
            data={"model": self.cfg.get("stt_groq_model", "whisper-large-v3-turbo"),
                  "language": "en", "response_format": "json", "temperature": "0"},
            files={"file": ("speech.wav", _wav(samples, self.rate), "audio/wav")})
        if response.status_code != 200:
            raise RuntimeError(f"{response.status_code} {response.text[:150]}")
        return response.json()["text"].strip()

    def request(self, samples, when=None):
        # Hand over an utterance. Returns immediately.
        if self.available is False:
            return False          # no model, so nothing to hand it to
        if samples is None or len(samples) < self.rate * 0.2:
            return False          # under 0.2 s, nothing worth transcribing
        try:
            self._queue.put_nowait((np.asarray(samples, dtype=np.float32),
                                    when if when is not None else time.time(),
                                    time.time()))
            return True
        except queue.Full:
            self.skipped += 1
            return False

    def latest(self):
        with self._lock:
            return self._text

    def latest_time(self):
        with self._lock:
            return self._text_t

    def latest_trace(self):
        with self._lock:
            return self._trace

    def clear(self):
        # Called when the robot disengages, so an old transcript does not
        # linger into the next interaction.
        with self._lock:
            self._text = ""
            self._text_t = None
            self._trace = None

    def _work(self):
        while not self._stop.is_set():
            try:
                samples, when, closed = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            started = time.time()
            t0 = time.perf_counter()

            # A little silence on the end. Whisper decides for itself
            # where speech stops, and audio that ends abruptly looks
            # truncated to it, so it drops the last word. Giving it a
            # clear ending is cheaper than guessing at the boundary.
            pad = self.cfg.get("stt_tail_pad_sec", 0.0)
            if pad:
                samples = np.concatenate([
                    samples,
                    np.zeros(round(pad * self.rate), dtype=np.float32)])

            text, engine = None, "local"
            if self._groq is not None:
                try:
                    text, engine = self._ask_groq(samples), "groq"
                except Exception as e:
                    print(f"Groq transcription failed, local used: {type(e).__name__} "
                          f"{str(e)[:120]}", flush=True)
            if text is None:
                try:
                    model = _get_model(self.cfg)
                    segments, _ = model.transcribe(
                        samples, language="en",
                        beam_size=self.cfg.get("stt_beam_size", 5))
                    text = " ".join(s.text.strip() for s in segments).strip()
                except Exception as e:
                    # One failure should not kill the thread, or every later
                    # utterance would be lost too.
                    print(f"transcription failed: {type(e).__name__}")
                    continue

            took = time.perf_counter() - t0
            audio_sec = len(samples) / self.rate
            self.done += 1

            with self._lock:
                self._text = text
                self._text_t = when
                self._trace = {"speech_end": round(when, 3), "closed": round(closed, 3),
                               "stt_start": round(started, 3), "stt_done": round(time.time(), 3)}

            if self.on_text is not None:
                self.on_text()

            if self.verbose:
                print(f"  TRANSCRIPT ({audio_sec:.1f}s audio in {took:.1f}s): "
                      f"{text!r}")
            elif self.log_timing:
                print(f"transcribed {audio_sec:.1f} s of audio in {took:.1f} s ({engine})", flush=True)