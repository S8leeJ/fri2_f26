"""Deepgram speech to text for one finished utterance.

    from stt import from_env

    text, ms = from_env().transcribe(audio_bytes, "audio/webm")

Uses DEEPGRAM_API_KEY from .env, the same key as tts.py. DEEPGRAM_STT_MODEL is optional.
"""

from __future__ import annotations

import os
import time
from typing import Tuple

import dotenv
import httpx

from tts import HERE, require_env

DEFAULT_MODEL = "nova-3"


class DeepgramSTT:
    name = "deepgram"

    def __init__(self, key: str, model: str = DEFAULT_MODEL, timeout_s: float = 10.0):
        self.model = model
        self.client = httpx.Client(base_url="https://api.deepgram.com",
                                   headers={"Authorization": "Token " + key}, timeout=timeout_s)

    def transcribe(self, audio: bytes, content_type: str) -> Tuple[str, float]:
        """Return (transcript, network ms). The transcript is "" when nothing was said."""
        start = time.perf_counter()
        response = self.client.post(
            "/v1/listen", content=audio, headers={"Content-Type": content_type},
            params={"model": self.model, "smart_format": "true", "language": "en"})
        if response.status_code != 200:
            raise RuntimeError("deepgram STT %d: %s" % (response.status_code, response.text[:200]))
        ms = (time.perf_counter() - start) * 1000
        alternatives = response.json()["results"]["channels"][0]["alternatives"]
        return (alternatives[0]["transcript"].strip() if alternatives else ""), ms


def from_env(**kwargs) -> DeepgramSTT:
    dotenv.load_dotenv(HERE / ".env")
    return DeepgramSTT(require_env("DEEPGRAM_API_KEY"),
                       os.environ.get("DEEPGRAM_STT_MODEL") or DEFAULT_MODEL, **kwargs)
