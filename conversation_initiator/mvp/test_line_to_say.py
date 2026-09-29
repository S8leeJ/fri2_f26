#!/usr/bin/env python3
"""Offline tests for the speech step in mvp.py. No API key, no network.

    python test_line_to_say.py
"""

from __future__ import annotations

import unittest
from unittest import mock

import mvp
from test_gate import base_ctx

RUBRIC = mvp.Rubric(invitation=5, interruption_cost=1, urgency=1, redundancy=1,
                    ambient_fit=5, addressivity=5)


def decision(action):
    return mvp.Decision6(rubric=RUBRIC, action=action, category="appropriate_to_initiate",
                         rule_fired="R5", confidence=0.9, recheck_in_ms=1000)


class LineToSayTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(mvp, "ask")
        self.ask = patcher.start()
        self.addCleanup(patcher.stop)
        self.ask.return_value = (mvp.Speech(text="Hello!", volume="medium", rate="medium",
                                            pitch="medium"), 500.0, None)

    def line(self, provider, ctx, action):
        return mvp.line_to_say(provider, None, "m", ctx, decision(action))

    def test_jev_greet_uses_fixed_line_without_a_call(self):
        speech, ms, err = self.line("jev", base_ctx(), "greet")
        self.assertIsNotNone(speech)
        self.assertEqual(speech.volume, "soft")
        self.assertIsNone(ms)
        self.assertIsNone(err)
        self.ask.assert_not_called()

    def test_fixed_line_volume_follows_room(self):
        for level, volume in (("quiet", "soft"), ("moderate", "medium"), ("loud", "loud")):
            speech, _, _ = self.line("jev", base_ctx(ambient={"noise_level": level}), "greet")
            self.assertEqual(speech.volume, volume)

    def test_jev_respond_reports_no_line(self):
        ctx = base_ctx(target={"speech": {"partial_transcript": "where is the lab?"}})
        self.assertEqual(self.line("jev", ctx, "respond"),
                         (None, None, "jev cannot write a reply"))
        self.ask.assert_not_called()

    def test_llm_greet_makes_the_speech_call(self):
        speech, ms, err = self.line("anthropic", base_ctx(), "greet")
        self.assertEqual(speech.text, "Hello!")
        self.assertEqual(ms, 500.0)
        self.ask.assert_called_once()

    def test_blocked_greet_skips_the_speech_call(self):
        ctx = base_ctx(target={"in_conversation": True})
        for provider in ("anthropic", "jev"):
            self.assertEqual(self.line(provider, ctx, "greet"), (None, None, None))
        self.ask.assert_not_called()

    def test_silence_skips_the_speech_call(self):
        self.assertEqual(self.line("anthropic", base_ctx(), "wait"), (None, None, None))
        self.ask.assert_not_called()


if __name__ == "__main__":
    unittest.main()
