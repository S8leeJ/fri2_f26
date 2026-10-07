#!/usr/bin/env python3
"""Offline tests for stt.py. No API key, no network.

    python test_stt.py
"""

from __future__ import annotations

import unittest

import httpx

from stt import DeepgramSTT


def reply(transcript):
    return {"results": {"channels": [{"alternatives": [{"transcript": transcript}]}]}}


class DeepgramSTTTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.response = httpx.Response(200, json=reply(" Where is the elevator? "))
        self.stt = DeepgramSTT("key")

        def handler(request):
            self.requests.append(request)
            return self.response

        self.stt.client = httpx.Client(base_url=self.stt.client.base_url,
                                       headers=self.stt.client.headers,
                                       transport=httpx.MockTransport(handler))

    def test_request_and_transcript(self):
        text, ms = self.stt.transcribe(b"webm-bytes", "audio/webm;codecs=opus")
        self.assertEqual(text, "Where is the elevator?")
        self.assertGreaterEqual(ms, 0)
        r = self.requests[0]
        self.assertEqual(r.url.path, "/v1/listen")
        self.assertEqual(r.content, b"webm-bytes")
        self.assertEqual(r.headers["Content-Type"], "audio/webm;codecs=opus")
        self.assertEqual(r.headers["Authorization"], "Token key")
        self.assertEqual(r.url.params["model"], "nova-3")

    def test_silence_is_empty(self):
        self.response = httpx.Response(200, json=reply(""))
        self.assertEqual(self.stt.transcribe(b"x", "audio/wav")[0], "")

    def test_error_raises(self):
        self.response = httpx.Response(400, text="bad audio")
        with self.assertRaisesRegex(RuntimeError, "deepgram STT 400"):
            self.stt.transcribe(b"x", "audio/wav")


if __name__ == "__main__":
    unittest.main()
