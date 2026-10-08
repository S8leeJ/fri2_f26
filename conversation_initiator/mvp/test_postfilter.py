#!/usr/bin/env python3
"""Offline tests for the post-filter. No API key, no network.

    python test_postfilter.py
"""

from __future__ import annotations

import json
import pathlib
import unittest

from postfilter import enforce
from test_gate import base_ctx

VIGNETTES = pathlib.Path(__file__).parent / "vignettes"


class PostfilterUnitTests(unittest.TestCase):
    def assertBlocked(self, ctx, action, rule):
        self.assertEqual(enforce(ctx, action), ("remain_silent", rule))

    def test_silence_always_passes(self):
        for action in ("remain_silent", "wait"):
            self.assertEqual(enforce(base_ctx(target=None), action), (action, None))

    def test_clear_greet_passes(self):
        self.assertEqual(enforce(base_ctx(), "greet"), ("greet", None))

    def test_no_person(self):
        self.assertBlocked(base_ctx(target=None), "greet", "no_person")

    def test_self_speaking(self):
        self.assertBlocked(base_ctx(robot={"is_speaking": True}), "greet", "self_speaking")

    def test_ignored_twice_blocks_both_speech_actions(self):
        ctx = base_ctx(robot={"consecutive_no_response": 2})
        self.assertBlocked(ctx, "greet", "R2 ignored twice")
        self.assertBlocked(ctx, "respond", "R2 ignored twice")

    def test_in_conversation(self):
        self.assertBlocked(base_ctx(target={"in_conversation": True}),
                           "greet", "R1 target in conversation")

    def test_spoke_recently_blocks_greet_not_respond(self):
        ctx = base_ctx(robot={"last_spoke_s_ago": 8.0},
                       target={"speech": {"partial_transcript": "where is room 2.302?"}})
        self.assertBlocked(ctx, "greet", "R2 spoke recently")
        self.assertEqual(enforce(ctx, "respond"), ("respond", None))

    def test_spoke_long_ago_passes(self):
        self.assertEqual(enforce(base_ctx(robot={"last_spoke_s_ago": 45.0}), "greet"),
                         ("greet", None))

    def test_respond_waits_while_mid_sentence(self):
        ctx = base_ctx(target={"speech": {"partial_transcript": "So I was wondering if you could",
                                          "syntactically_complete": False}})
        self.assertEqual(enforce(ctx, "respond"), ("wait", "person mid-sentence"))

    def test_respond_passes_when_complete_or_unknown(self):
        for complete in (True, None):
            speech = {"partial_transcript": "Where is the elevator?"}
            if complete is not None:
                speech["syntactically_complete"] = complete
            self.assertEqual(enforce(base_ctx(target={"speech": speech}), "respond"),
                             ("respond", None))

    def test_respond_needs_transcript(self):
        self.assertBlocked(base_ctx(), "respond", "respond without transcript")
        self.assertBlocked(base_ctx(target={"speech": None}), "respond",
                           "respond without transcript")


class PostfilterVignetteTests(unittest.TestCase):
    """A greet forced onto every labelled vignette."""

    def setUp(self):
        self.vignettes = [json.loads(f.read_text()) for f in sorted(VIGNETTES.glob("*.json"))]

    def test_never_blocks_a_labelled_greet(self):
        for v in self.vignettes:
            if v.get("expect") == "greet":
                with self.subTest(v["id"]):
                    self.assertEqual(enforce(v["context"], "greet"), ("greet", None))

    def test_blocks_greet_on_hard_rule_vignettes(self):
        expected = {"002": "R1 target in conversation",
                    "005": "R2 ignored twice",
                    "008": "R1 target in conversation",
                    "009": "self_speaking"}
        by_id = {v["id"]: v for v in self.vignettes}
        for vid, rule in expected.items():
            with self.subTest(vid):
                self.assertEqual(enforce(by_id[vid]["context"], "greet"), ("remain_silent", rule))


if __name__ == "__main__":
    unittest.main()
