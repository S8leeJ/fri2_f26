#!/usr/bin/env python3
"""Offline tests for prosody.py and tts.py. No API key, no network.

    python test_tts.py
"""

from __future__ import annotations

import itertools
import os
import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest import mock

import httpx

from prosody import PITCHES, RATES, VOLUMES, to_ssml
from tts import TTS

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


class TTSTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.requests = []
        self.status = 200

        def handler(request):
            self.requests.append(request)
            return httpx.Response(self.status, content=b"RIFFfake")

        self.tts = TTS("key", "eastus", cache_dir=pathlib.Path(tmp.name))
        self.tts.client = httpx.Client(base_url="https://eastus.tts.speech.microsoft.com",
                                       transport=httpx.MockTransport(handler))

    def test_first_call_synthesizes_then_cache_hits(self):
        path, ms = self.tts.synthesize(line())
        self.assertIsNotNone(ms)
        self.assertEqual(path.read_bytes(), b"RIFFfake")
        path2, ms2 = self.tts.synthesize(line())
        self.assertEqual((path2, ms2), (path, None))
        self.assertEqual(len(self.requests), 1)

    def test_different_volume_is_a_different_file(self):
        a, _ = self.tts.synthesize(line(volume="soft"))
        b, _ = self.tts.synthesize(line(volume="loud"))
        self.assertNotEqual(a, b)
        self.assertEqual(len(self.requests), 2)

    def test_request_sends_ssml(self):
        self.tts.synthesize(line(text="Hello"))
        self.assertIn(b"<prosody", self.requests[0].content)
        self.assertTrue(self.requests[0].url.path.endswith("/cognitiveservices/v1"))

    def test_error_raises_and_caches_nothing(self):
        self.status = 401
        with self.assertRaises(RuntimeError):
            self.tts.synthesize(line())
        self.assertEqual(list(self.tts.cache_dir.iterdir()), [])

    def test_missing_key_names_it(self):
        with mock.patch.dict(os.environ, {"AZURE_SPEECH_KEY": "", "AZURE_SPEECH_REGION": ""}), \
                mock.patch("tts.dotenv.load_dotenv"):
            with self.assertRaisesRegex(RuntimeError, "AZURE_SPEECH_KEY"):
                TTS.from_env()


if __name__ == "__main__":
    unittest.main()
