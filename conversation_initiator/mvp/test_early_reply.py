#!/usr/bin/env python3
"""Offline tests for the early reply in mvp.decide. No API key, no network.

    python test_early_reply.py
"""

from __future__ import annotations

import json
import time
import unittest
from unittest import mock

import mvp
from test_gate import base_ctx
from test_line_to_say import decision

DECIDE_S, WRITE_S = 0.15, 0.25
HEARD = {"speech": {"detected": True, "partial_transcript": "What is this lab?",
                    "syntactically_complete": True}}
LINE = mvp.Speech(text="It is a robotics lab.", volume="medium", rate="medium", pitch="medium")


class EarlyReplyTests(unittest.TestCase):
    def run_decide(self, action, ctx, early, writer_fails=False):
        """Returns (result, seconds, calls). calls: (schema name, start, user JSON) in start order."""
        calls = []

        def ask(provider, client, model, system, user, schema, max_tokens):
            calls.append((schema.__name__, time.perf_counter(), json.loads(user)))
            if schema is mvp.Speech:
                time.sleep(WRITE_S)
                if writer_fails:
                    raise RuntimeError("writer down")
                return LINE, WRITE_S * 1000, None
            time.sleep(DECIDE_S)
            return decision(action), DECIDE_S * 1000, None

        mvp.use_rules(False)
        self.addCleanup(mvp.use_rules, True)
        with mock.patch.object(mvp, "ask", ask),                 mock.patch.object(mvp, "reply_writers", lambda: [("groq", None, "writer")]):
            start = time.perf_counter()
            result = mvp.decide("jev", None, "jev-latest", ctx, 6, early_reply=early)
            took = time.perf_counter() - start
        return result, took, sorted(calls, key=lambda c: c[1])

    def test_reply_is_written_while_the_decision_is_made(self):
        r, took, calls = self.run_decide("respond", base_ctx(target=HEARD), early=True)
        self.assertEqual(r.speech, LINE)
        self.assertLess(took, DECIDE_S + WRITE_S - 0.05)
        self.assertLess(abs(calls[0][1] - calls[1][1]), 0.05)
        writer = next(c for c in calls if c[0] == "Speech")
        self.assertEqual(writer[2]["decision"], {"action": "respond"})
        self.assertAlmostEqual(r.line_wait_ms, (WRITE_S - DECIDE_S) * 1000, delta=60)

    def test_serial_reply_waits_for_the_decision(self):
        r, took, calls = self.run_decide("respond", base_ctx(target=HEARD), early=False)
        self.assertEqual(r.speech, LINE)
        self.assertGreaterEqual(took, DECIDE_S + WRITE_S - 0.02)
        self.assertEqual([c[0] for c in calls], ["Decision6", "Speech"])
        self.assertEqual(calls[1][2]["decision"]["rule_fired"], "R5")
        self.assertIsNone(r.line_wait_ms)

    def test_early_reply_is_dropped_when_the_decision_is_not_respond(self):
        for action in ("remain_silent", "wait"):
            with self.subTest(action):
                r, took, _ = self.run_decide(action, base_ctx(target=HEARD), early=True)
                self.assertIsNone(r.speech)
                self.assertIsNone(r.speech_error)
                self.assertLess(took, DECIDE_S + 0.08)

    def test_greet_still_uses_the_fixed_line(self):
        r, _, _ = self.run_decide("greet", base_ctx(target=HEARD), early=True)
        self.assertEqual(r.speech, mvp.fixed_greeting(base_ctx()))

    def test_no_early_reply_without_a_finished_sentence(self):
        unfinished = {"speech": {**HEARD["speech"], "syntactically_complete": False}}
        for name, ctx in (("no transcript", base_ctx()), ("mid-sentence", base_ctx(target=unfinished)),
                          ("nobody", base_ctx(target=None))):
            with self.subTest(name):
                r, _, calls = self.run_decide("remain_silent", ctx, early=True)
                self.assertEqual([c[0] for c in calls], ["Decision6"])
                self.assertIsNone(r.speech)

    def test_a_failed_early_reply_reports_the_error(self):
        r, _, _ = self.run_decide("respond", base_ctx(target=HEARD), early=True, writer_fails=True)
        self.assertIsNone(r.speech)
        self.assertIn("writer down", r.speech_error)
        self.assertEqual(r.action, "respond")


if __name__ == "__main__":
    unittest.main()
