#!/usr/bin/env python3
"""Offline tests for the speech step in mvp.py. No API key, no network.

    python test_line_to_say.py
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
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

    def ask_jev(self, rules_on):
        sent = {}

        class Client:
            def post(self, path, json):
                sent.update(json)
                answers = {d: {"score": 1.0} for d in mvp.Rubric.model_fields}
                answers["action"] = {"choice": "remain_silent", "confidence": 0.8}
                answers["category"] = {"choice": "insufficient_evidence"}
                answers["rule_fired"] = {"choice": "R6"}
                return mock.Mock(status_code=200, json=lambda: {"answers": answers})

        mvp.use_rules(rules_on)
        self.addCleanup(mvp.use_rules, True)
        d, _ = mvp._ask_jev(Client(), "jev-latest", None, '{"t": 0}', mvp.Decision6, 400)
        return d, sent["questions"]

    def test_jev_with_rules_gets_the_rules(self):
        d, questions = self.ask_jev(True)
        self.assertIn("rule_fired", questions)
        self.assertIn("rules", questions["action"]["instructions"])
        self.assertTrue(d.rule_fired.startswith("R6"))

    def test_jev_without_rules_gets_only_the_scene(self):
        d, questions = self.ask_jev(False)
        self.assertNotIn("rule_fired", questions)
        text = json.dumps(questions)
        for rule in ("R1", "R2", "R3", "R4", "R5", "R6", "rules"):
            self.assertNotIn(rule, text)
        self.assertEqual((d.action, d.rule_fired), ("remain_silent", ""))


class SceneOnlyPromptTests(unittest.TestCase):
    def test_scene_prompts_hold_no_rules(self):
        for prompt in (mvp.SYSTEM_6_SCENE, mvp.SYSTEM_3_SCENE):
            self.assertNotRegex(prompt, r"\bR[1-6]\b")
            self.assertNotIn("Rules, in priority order", prompt)
            self.assertIn("Score", prompt)

    def test_rule_prompts_are_unchanged(self):
        self.assertIn("Rules, in priority order", mvp.SYSTEM_6)
        self.assertIn("R5 Greet when the person faces the robot", mvp.SYSTEM_6)

    def test_decide_sends_the_prompt_for_the_mode(self):
        d = decision("remain_silent")
        with mock.patch.object(mvp, "ask", return_value=(d, 100.0, None)) as ask:
            mvp.use_rules(False)
            self.addCleanup(mvp.use_rules, True)
            mvp.decide("anthropic", None, "m", base_ctx(), 6)
            self.assertEqual(ask.call_args.args[3], mvp.SYSTEM_6_SCENE)
            mvp.use_rules(True)
            mvp.decide("anthropic", None, "m", base_ctx(), 6)
            self.assertEqual(ask.call_args.args[3], mvp.SYSTEM_6)


# Each spoken line sends the facts again, and Groq's free tier is 8,000 tokens a minute.
FACTS_BUDGET_CHARS = 4000


class FactsTests(unittest.TestCase):
    def test_facts_file_is_in_the_prompt(self):
        self.assertTrue(mvp.FACTS_PATH.exists())
        self.assertIn("Anna Hiss Gymnasium", mvp.FACTS)
        self.assertIn("Living with Robots Lab, Dr. Justin Hart", mvp.FACTS)
        self.assertTrue(mvp.SPEECH_SYSTEM.endswith(mvp.FACTS))

    def test_sources_stay_out_of_the_prompt(self):
        self.assertIn("## Sources", mvp.FACTS_PATH.read_text())
        self.assertNotIn("## Sources", mvp.FACTS)

    def test_facts_fit_the_budget(self):
        self.assertLess(len(mvp.FACTS), FACTS_BUDGET_CHARS)

    def test_prompt_says_to_admit_not_knowing(self):
        self.assertIn("don't know that yet", mvp.SPEECH_SYSTEM)
        self.assertIn("Never guess", mvp.SPEECH_SYSTEM)

    def test_missing_file_means_no_facts(self):
        missing = pathlib.Path(tempfile.gettempdir()) / "no_such_facts.md"
        self.assertEqual(mvp.load_facts(missing), "You know no facts about the building.")


class ReplyWriterTests(unittest.TestCase):
    def setUp(self):
        mvp._reply_writers = None
        self.addCleanup(setattr, mvp, "_reply_writers", None)
        patcher = mock.patch.object(mvp, "make_client", side_effect=lambda p, t: p + "-client")
        patcher.start()
        self.addCleanup(patcher.stop)

    def env(self, **values):
        base = {"GROQ_API_KEY": "", "GEMINI_API_KEY": "",
                "ANTHROPIC_API_KEY": ""}
        return mock.patch.dict(os.environ, {**base, **values})

    def names(self):
        return [w[0] for w in mvp.reply_writers()]

    def test_writers_with_a_key_in_order(self):
        with self.env(GEMINI_API_KEY="k", ANTHROPIC_API_KEY="k", GROQ_API_KEY="k"):
            self.assertEqual(self.names(), ["groq", "anthropic", "gemini"])
        mvp._reply_writers = None
        with self.env(GEMINI_API_KEY="k", ANTHROPIC_API_KEY="k"):
            self.assertEqual(self.names(), ["anthropic", "gemini"])

    def test_groq_model_setting(self):
        with self.env(GROQ_API_KEY="k", GROQ_MODEL="openai/gpt-oss-120b"):
            self.assertEqual(mvp.reply_writers()[0][2], "openai/gpt-oss-120b")
        mvp._reply_writers = None
        with self.env(GROQ_API_KEY="k", GROQ_MODEL=""):
            self.assertEqual(mvp.reply_writers()[0][2], mvp.DEFAULT_MODEL["groq"])

    def test_groq_first_even_with_the_old_setting(self):
        with self.env(JEV_REPLY_PROVIDER="anthropic", GROQ_API_KEY="k", ANTHROPIC_API_KEY="k"):
            self.assertEqual(self.names(), ["groq", "anthropic"])

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

    def test_without_rules_a_greet_to_a_busy_person_gets_a_line(self):
        mvp.use_rules(False)
        self.addCleanup(mvp.use_rules, True)
        ctx = base_ctx(target={"in_conversation": True}, robot={"last_spoke_s_ago": 5.0})
        speech, _, _ = self.line("jev", ctx, "greet")
        self.assertIsNotNone(speech)

    def test_silence_skips_the_speech_call(self):
        self.assertEqual(self.line("anthropic", base_ctx(), "wait"), (None, None, None))
        self.ask.assert_not_called()


if __name__ == "__main__":
    unittest.main()
