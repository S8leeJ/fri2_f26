#!/usr/bin/env python3
"""Text to speech with a disk cache. Deepgram is the default. Azure is the other option.

A fixed line, such as the greeting, is synthesized once. Later calls play it
from disk with no network call.

Deepgram has no volume or pitch control. Volume is applied here by scaling
the samples, so one Deepgram clip serves every volume. Pitch is ignored.

Usage:  python3 tts.py --warm                       # cache the 3 greetings
        python3 tts.py "Hello there" --volume loud  # synthesize and play one line

.env: DEEPGRAM_API_KEY, optional DEEPGRAM_VOICE.
      For Azure: TTS_PROVIDER=azure, AZURE_SPEECH_KEY, AZURE_SPEECH_REGION,
      optional AZURE_SPEECH_VOICE.
"""

from __future__ import annotations

import argparse
import array
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import time
import wave
from types import SimpleNamespace
from typing import Optional, Tuple

import dotenv
import httpx

from prosody import DEFAULT_VOICE, PITCHES, RATES, VOLUMES, to_ssml

HERE = pathlib.Path(__file__).parent
CACHE = HERE / "tts_cache"

DEFAULT_DEEPGRAM_VOICE = "aura-2-thalia-en"
SAMPLE_RATE = 24000
RATE_TO_SPEED = {"slow": 0.85, "medium": 1.0, "fast": 1.15}
# Gain never exceeds 1.0, so scaling cannot clip.
VOLUME_GAIN = {"x-soft": 0.25, "soft": 0.5, "medium": 0.7, "loud": 1.0}


def scale_pcm(pcm: bytes, gain: float) -> bytes:
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if sys.byteorder != "little":
        samples.byteswap()
    scaled = array.array("h", (int(s * gain) for s in samples))
    if sys.byteorder != "little":
        scaled.byteswap()
    return scaled.tobytes()


def wav_bytes(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


class _CachedTTS:
    name = ""

    def __init__(self, base_url: str, headers: dict, cache_dir: pathlib.Path, timeout_s: float):
        self.cache_dir = cache_dir
        self.client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout_s)

    def _path(self, *parts, suffix: str = ".wav") -> pathlib.Path:
        digest = hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:16]
        return self.cache_dir / (digest + suffix)

    def _save(self, path: pathlib.Path, data: bytes) -> None:
        self.cache_dir.mkdir(exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)

    def _post(self, url: str, **kwargs) -> Tuple[bytes, float]:
        start = time.perf_counter()
        response = self.client.post(url, **kwargs)
        if response.status_code != 200:
            raise RuntimeError("%s TTS %d: %s"
                               % (self.name, response.status_code, response.text[:200]))
        return response.content, (time.perf_counter() - start) * 1000


class DeepgramTTS(_CachedTTS):
    name = "deepgram"

    def __init__(self, key: str, voice: str = DEFAULT_DEEPGRAM_VOICE,
                 cache_dir: pathlib.Path = CACHE, timeout_s: float = 5.0):
        super().__init__("https://api.deepgram.com", {"Authorization": "Token " + key},
                         cache_dir, timeout_s)
        self.voice = voice

    def synthesize(self, speech) -> Tuple[pathlib.Path, Optional[float]]:
        """Return (wav path, network ms). ms is None when no call was made."""
        gain, speed = VOLUME_GAIN[speech.volume], RATE_TO_SPEED[speech.rate]
        path = self._path(self.voice, speech.text, speed, gain)
        if path.exists():
            return path, None
        raw = self._path(self.voice, speech.text, speed, suffix=".pcm")
        ms = None
        if raw.exists():
            pcm = raw.read_bytes()
        else:
            pcm, ms = self._post("/v1/speak", json={"text": speech.text}, params={
                "model": self.voice, "encoding": "linear16", "container": "none",
                "sample_rate": SAMPLE_RATE, "speed": speed})
            self._save(raw, pcm)
        self._save(path, wav_bytes(scale_pcm(pcm, gain)))
        return path, ms


class AzureTTS(_CachedTTS):
    name = "azure"

    def __init__(self, key: str, region: str, voice: str = DEFAULT_VOICE,
                 cache_dir: pathlib.Path = CACHE, timeout_s: float = 5.0):
        super().__init__("https://%s.tts.speech.microsoft.com" % region,
                         {"Ocp-Apim-Subscription-Key": key,
                          "Content-Type": "application/ssml+xml",
                          "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
                          "User-Agent": "fri2-conversation-initiator"},
                         cache_dir, timeout_s)
        self.voice = voice

    def synthesize(self, speech) -> Tuple[pathlib.Path, Optional[float]]:
        """Return (wav path, network ms). ms is None on a cache hit."""
        ssml = to_ssml(speech, self.voice)
        path = self._path(ssml)
        if path.exists():
            return path, None
        audio, ms = self._post("/cognitiveservices/v1", content=ssml.encode())
        self._save(path, audio)
        return path, ms


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("%s not set in .env." % name)
    return value


def from_env(**kwargs):
    dotenv.load_dotenv(HERE / ".env")
    provider = os.environ.get("TTS_PROVIDER") or "deepgram"
    if provider == "deepgram":
        return DeepgramTTS(require_env("DEEPGRAM_API_KEY"),
                           os.environ.get("DEEPGRAM_VOICE") or DEFAULT_DEEPGRAM_VOICE, **kwargs)
    if provider == "azure":
        return AzureTTS(require_env("AZURE_SPEECH_KEY"), require_env("AZURE_SPEECH_REGION"),
                        os.environ.get("AZURE_SPEECH_VOICE") or DEFAULT_VOICE, **kwargs)
    raise RuntimeError("TTS_PROVIDER must be deepgram or azure, not %r." % provider)


def play(path: pathlib.Path) -> None:
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)
    elif sys.platform == "darwin":
        subprocess.run(["afplay", str(path)], check=True)
    else:
        subprocess.run(["aplay", "-q", str(path)], check=True)


def main() -> None:
    from mvp import VOLUME_FOR_NOISE, fixed_greeting

    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?")
    ap.add_argument("--volume", default="medium", choices=VOLUMES)
    ap.add_argument("--rate", default="medium", choices=RATES)
    ap.add_argument("--pitch", default="medium", choices=PITCHES,
                    help="Azure only. Deepgram ignores it.")
    ap.add_argument("--warm", action="store_true", help="cache one greeting per noise level")
    ap.add_argument("--no-play", action="store_true")
    args = ap.parse_args()

    try:
        tts = from_env()
    except RuntimeError as e:
        sys.exit(str(e))
    if args.warm:
        lines = [fixed_greeting({"ambient": {"noise_level": level}}) for level in VOLUME_FOR_NOISE]
    elif args.text:
        lines = [SimpleNamespace(text=args.text, volume=args.volume, rate=args.rate,
                                 pitch=args.pitch)]
    else:
        ap.error("give a line to say, or --warm")

    for speech in lines:
        path, ms = tts.synthesize(speech)
        print("%s %-7s %s  %s" % (tts.name, speech.volume,
                                  "cached" if ms is None else "%.0f ms" % ms, path))
        if not args.no_play:
            play(path)


if __name__ == "__main__":
    main()
