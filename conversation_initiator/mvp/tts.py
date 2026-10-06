#!/usr/bin/env python3
"""Azure text to speech, with a disk cache keyed by the SSML.

A fixed line, such as the greeting, is synthesized once. Later calls play it
from disk with no network call.

Usage:  python3 tts.py --warm                       # cache the 3 greetings
        python3 tts.py "Hello there" --volume loud  # synthesize and play one line

Needs AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in .env. AZURE_SPEECH_VOICE is optional.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Optional, Tuple

import dotenv
import httpx

from prosody import DEFAULT_VOICE, PITCHES, RATES, VOLUMES, to_ssml

HERE = pathlib.Path(__file__).parent
CACHE = HERE / "tts_cache"
OUTPUT_FORMAT = "riff-24khz-16bit-mono-pcm"


class TTS:
    def __init__(self, key: str, region: str, voice: str = DEFAULT_VOICE,
                 cache_dir: pathlib.Path = CACHE, timeout_s: float = 5.0):
        self.voice = voice
        self.cache_dir = cache_dir
        self.client = httpx.Client(
            base_url="https://%s.tts.speech.microsoft.com" % region,
            headers={"Ocp-Apim-Subscription-Key": key,
                     "Content-Type": "application/ssml+xml",
                     "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
                     "User-Agent": "fri2-conversation-initiator"},
            timeout=timeout_s,
        )

    @classmethod
    def from_env(cls, **kwargs) -> "TTS":
        dotenv.load_dotenv(HERE / ".env")
        missing = [k for k in ("AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION") if not os.environ.get(k)]
        if missing:
            raise RuntimeError("%s not set in .env." % " and ".join(missing))
        return cls(os.environ["AZURE_SPEECH_KEY"], os.environ["AZURE_SPEECH_REGION"],
                   os.environ.get("AZURE_SPEECH_VOICE") or DEFAULT_VOICE, **kwargs)

    def cache_path(self, ssml: str) -> pathlib.Path:
        return self.cache_dir / (hashlib.sha256(ssml.encode()).hexdigest()[:16] + ".wav")

    def synthesize(self, speech) -> Tuple[pathlib.Path, Optional[float]]:
        """Return (wav path, network ms). ms is None on a cache hit."""
        ssml = to_ssml(speech, self.voice)
        path = self.cache_path(ssml)
        if path.exists():
            return path, None
        start = time.perf_counter()
        response = self.client.post("/cognitiveservices/v1", content=ssml.encode())
        if response.status_code != 200:
            raise RuntimeError("Azure TTS %d: %s" % (response.status_code, response.text[:200]))
        ms = (time.perf_counter() - start) * 1000
        self.cache_dir.mkdir(exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(response.content)
        tmp.replace(path)
        return path, ms


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
    ap.add_argument("--pitch", default="medium", choices=PITCHES)
    ap.add_argument("--warm", action="store_true", help="cache one greeting per noise level")
    ap.add_argument("--no-play", action="store_true")
    args = ap.parse_args()

    try:
        tts = TTS.from_env()
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
        print("%-7s %s  %s" % (speech.volume, "cached" if ms is None else "%.0f ms" % ms, path))
        if not args.no_play:
            play(path)


if __name__ == "__main__":
    main()
