#!/usr/bin/env python3
"""Offline tests for prosody.py and tts.py. No API key, no network.

    python test_tts.py
"""

from __future__ import annotations

import array
import itertools
import json
import os
import pathlib
import tempfile
import unittest
import wave
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest import mock

import httpx

from prosody import PITCHES, RATES, VOLUMES, to_ssml
from tts import AzureTTS, DeepgramTTS, from_env, scale_pcm

NS = "{http://www.w3.org/2001/10/synthesis}"


def line(text="Hi there!", volume="medium", rate="medium", pitch="medium"):
    return SimpleNamespace(text=text, volume=volume, rate=rate, pitch=pitch)


class ProsodyTests(unittest.TestCase):
    def test_every_combination_is_valid_xml(self):
        for v, r, p in itertools.product(VOLUMES, RATES, PITCHES):
            with self.subTest(v=v, r=r, p=p):
                prosody = ET.fromstring(to_ssml(line(volume=v, rate=r, pitch=p))).find(
                    "%svoice/%sprosody" % (NS, NS))
                self.assertEqual((prosody.get("volume"), prosody.get("rate"),
                                  prosody.get("pitch")), (v, r, p))

    def test_text_is_escaped(self):
        text = 'Tom & Jerry <say> "hi"'
        root = ET.fromstring(to_ssml(line(text=text)))
        self.assertEqual(root.find("%svoice/%sprosody" % (NS, NS)).text, text)

    def test_voice_is_set(self):
        root = ET.fromstring(to_ssml(line(), voice="en-US-AvaNeural"))
        self.assertEqual(root.find(NS + "voice").get("name"), "en-US-AvaNeural")

    def test_unknown_enum_is_rejected(self):
        with self.assertRaises(ValueError):
            to_ssml(line(volume="x-loud"))


PCM = array.array("h", [1000, -1000, 32767, -32768]).tobytes()


def samples(path):
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        return array.array("h", w.readframes(w.getnframes())).tolist()


class _FakeServer(unittest.TestCase):
    def fake(self, tts, body):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tts.cache_dir = pathlib.Path(tmp.name)
        self.requests = []
        self.status = 200

        def handler(request):
            self.requests.append(request)
            return httpx.Response(self.status, content=body)

        tts.client = httpx.Client(base_url=tts.client.base_url, headers=tts.client.headers,
                                  transport=httpx.MockTransport(handler))
        return tts


class DeepgramTests(_FakeServer):
    def setUp(self):
        self.tts = self.fake(DeepgramTTS("key"), PCM)

    def test_request_shape(self):
        self.tts.synthesize(line(text="Hello", rate="slow"))
        r = self.requests[0]
        self.assertEqual(r.url.path, "/v1/speak")
        self.assertEqual(r.headers["Authorization"], "Token key")
        self.assertEqual(json.loads(r.content), {"text": "Hello"})
        self.assertEqual(dict(r.url.params), {
            "model": "aura-2-thalia-en", "encoding": "linear16", "container": "none",
            "sample_rate": "24000", "speed": "0.85"})

    def test_loud_is_unscaled_wav_then_cached(self):
        path, ms = self.tts.synthesize(line(volume="loud"))
        self.assertIsNotNone(ms)
        self.assertEqual(samples(path), [1000, -1000, 32767, -32768])
        self.assertEqual(self.tts.synthesize(line(volume="loud")), (path, None))
        self.assertEqual(len(self.requests), 1)

    def test_other_volumes_reuse_one_clip(self):
        loud, _ = self.tts.synthesize(line(volume="loud"))
        soft, ms = self.tts.synthesize(line(volume="soft"))
        self.assertIsNone(ms)
        self.assertNotEqual(soft, loud)
        self.assertEqual(samples(soft), [500, -500, 16383, -16384])
        self.assertEqual(len(self.requests), 1)

    def test_new_rate_is_a_new_call(self):
        self.tts.synthesize(line(rate="medium"))
        self.tts.synthesize(line(rate="fast"))
        self.assertEqual([r.url.params["speed"] for r in self.requests], ["1.0", "1.15"])

    def test_pitch_is_ignored(self):
        a, _ = self.tts.synthesize(line(pitch="low"))
        b, _ = self.tts.synthesize(line(pitch="high"))
        self.assertEqual(a, b)
        self.assertEqual(len(self.requests), 1)

    def test_error_raises_and_caches_nothing(self):
        self.status = 401
        with self.assertRaisesRegex(RuntimeError, "deepgram TTS 401"):
            self.tts.synthesize(line())
        self.assertFalse(self.tts.cache_dir.exists() and any(self.tts.cache_dir.iterdir()))

    def test_scale_pcm_drops_a_trailing_odd_byte(self):
        self.assertEqual(scale_pcm(PCM + b"x", 1.0), PCM)


class AzureTests(_FakeServer):
    def setUp(self):
        self.tts = self.fake(AzureTTS("key", "eastus"), b"RIFFfake")

    def test_first_call_synthesizes_then_cache_hits(self):
        path, ms = self.tts.synthesize(line())
        self.assertIsNotNone(ms)
        self.assertEqual(path.read_bytes(), b"RIFFfake")
        self.assertEqual(self.tts.synthesize(line()), (path, None))
        self.assertEqual(len(self.requests), 1)

    def test_request_sends_ssml(self):
        self.tts.synthesize(line(text="Hello"))
        self.assertIn(b"<prosody", self.requests[0].content)
        self.assertEqual(self.requests[0].url.path, "/cognitiveservices/v1")
        self.assertEqual(self.requests[0].headers["Ocp-Apim-Subscription-Key"], "key")


class FromEnvTests(unittest.TestCase):
    def env(self, **values):
        base = {"TTS_PROVIDER": "", "DEEPGRAM_API_KEY": "", "AZURE_SPEECH_KEY": "",
                "AZURE_SPEECH_REGION": ""}
        return mock.patch.dict(os.environ, {**base, **values})

    def setUp(self):
        patcher = mock.patch("tts.dotenv.load_dotenv")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_deepgram_is_the_default(self):
        with self.env(DEEPGRAM_API_KEY="k"):
            self.assertIsInstance(from_env(), DeepgramTTS)
        with self.env(), self.assertRaisesRegex(RuntimeError, "DEEPGRAM_API_KEY"):
            from_env()

    def test_azure_on_request(self):
        with self.env(TTS_PROVIDER="azure", AZURE_SPEECH_KEY="k", AZURE_SPEECH_REGION="eastus"):
            self.assertIsInstance(from_env(), AzureTTS)
        with self.env(TTS_PROVIDER="azure"), self.assertRaisesRegex(RuntimeError, "AZURE_SPEECH_KEY"):
            from_env()

    def test_unknown_provider(self):
        with self.env(TTS_PROVIDER="polly"), self.assertRaisesRegex(RuntimeError, "polly"):
            from_env()


if __name__ == "__main__":
    unittest.main()
