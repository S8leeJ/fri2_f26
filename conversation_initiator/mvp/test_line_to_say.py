#!/usr/bin/env python3
"""Offline tests for the speech step in mvp.py. No API key, no network.

    python test_line_to_say.py
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

import mvp
from test_gate import base_ctx

RUBRIC = mvp.Rubric(invitation=5, interruption_cost=1, urgency=1, redundancy=1,
                    ambient_fit=5, addressivity=5)


def decision(action):
    return mvp.Decision6(rubric=RUBRIC, action=action, category="appropriate_to_initiate",
                         rule_fired="R5", confidence=0.9, recheck_in_ms=1000)


class JevQuestionTests(unittest.TestCase):
    def test_rule_choices_are_only_the_rules(self):
        self.assertEqual(list(mvp.RULE_TEXT), ["R1", "R2", "R3", "R4", "R5", "R6"])
        self.assertTrue(mvp.RULE_TEXT["R1"].startswith("Never greet someone who is in a conversation"))


class ReplyWriterTests(unittest.TestCase):
    def setUp(self):
        mvp._reply_writers = None
        self.addCleanup(setattr, mvp, "_reply_writers", None)
        patcher = mock.patch.object(mvp, "make_client", side_effect=lambda p, t: p + "-client")
        patcher.start()
        self.addCleanup(patcher.stop)

    def env(self, **values):
        base = {"JEV_REPLY_PROVIDER": "", "GROQ_API_KEY": "", "GEMINI_API_KEY": "",
                "ANTHROPIC_API_KEY": ""}
        return mock.patch.dict(os.environ, {**base, **values})

    def names(self):
        return [w[0] for w in mvp.reply_writers()]

    def test_writers_with_a_key_in_order(self):
        with self.env(GEMINI_API_KEY="k", ANTHROPIC_API_KEY="k"):
            self.assertEqual(self.names(), ["gemini", "anthropic"])

    def test_override_goes_first(self):
        with self.env(JEV_REPLY_PROVIDER="anthropic", GROQ_API_KEY="k", ANTHROPIC_API_KEY="k"):
            self.assertEqual(self.names(), ["anthropic", "groq"])

    def test_none_without_keys(self):
        with self.env():
            self.assertEqual(mvp.reply_writers(), [])


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

    def test_jev_respond_without_a_writer_reports_no_line(self):
        ctx = base_ctx(target={"speech": {"partial_transcript": "where is the lab?"}})
        with mock.patch.object(mvp, "reply_writers", return_value=[]):
            speech, ms, err = self.line("jev", ctx, "respond")
        self.assertEqual((speech, ms), (None, None))
        self.assertIn("jev cannot write a reply", err)
        self.ask.assert_not_called()

    def test_jev_respond_uses_the_writer(self):
        ctx = base_ctx(target={"speech": {"partial_transcript": "where is the lab?"}})
        with mock.patch.object(mvp, "reply_writers", return_value=[("groq", "groq-client", "gpt")]):
            speech, ms, err = self.line("jev", ctx, "respond")
        self.assertEqual((speech.text, ms, err), ("Hello!", 500.0, None))
        provider, client, model = self.ask.call_args.args[:3]
        self.assertEqual((provider, client, model), ("groq", "groq-client", "gpt"))

    def test_jev_respond_falls_back_to_the_next_writer(self):
        ctx = base_ctx(target={"speech": {"partial_transcript": "where is the lab?"}})
        ok = self.ask.return_value
        self.ask.side_effect = [RuntimeError("400 json_validate_failed"), ok]
        writers = [("groq", "g", "m1"), ("gemini", "c", "m2")]
        with mock.patch.object(mvp, "reply_writers", return_value=writers):
            speech, _, err = self.line("jev", ctx, "respond")
        self.assertEqual((speech.text, err), ("Hello!", None))
        self.assertEqual([c.args[0] for c in self.ask.call_args_list], ["groq", "gemini"])

    def test_every_writer_failing_names_the_last_error(self):
        ctx = base_ctx(target={"speech": {"partial_transcript": "where is the lab?"}})
        self.ask.side_effect = RuntimeError("boom")
        with mock.patch.object(mvp, "reply_writers", return_value=[("groq", "g", "m"), ("gemini", "c", "m")]):
            self.assertEqual(self.line("jev", ctx, "respond"), (None, None, "gemini: boom"))

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
