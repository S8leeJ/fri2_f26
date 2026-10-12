#!/usr/bin/env python3
"""Offline tests for the turn trace. No ROS, no network.

    python test_turn_trace.py
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from turn_trace import Tracer, steps

FULL = {"speech_end": 100.0, "closed": 100.5, "stt_done": 101.1, "built": 101.6,
        "arrived": 101.7, "seen": 101.9, "asked": 102.0}


class TurnTraceTests(unittest.TestCase):
    def test_every_step_from_a_full_trace(self):
        got = dict(steps(FULL, 700, 400, 0.3))
        want = {"close": 0.5, "stt": 0.6, "publish": 0.5, "fusion": 0.1, "tick": 0.2,
                "gate": 0.1, "decide": 0.7, "line": 0.4, "tts": 0.3}
        self.assertEqual(list(got), list(want))
        for k, v in want.items():
            self.assertAlmostEqual(got[k], v, places=6)

    def test_without_an_audio_trace_only_the_wait_is_known(self):
        got = dict(steps({"speech_end": 100.0, "seen": 101.5, "asked": 102.0}, 700, None, None))
        self.assertEqual(list(got), ["heard", "gate", "decide"])
        self.assertAlmostEqual(got["heard"], 1.5)

    def test_add_logs_one_row_and_summary_has_each_step(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "trace.jsonl"
            tracer = Tracer(path)
            line = tracer.add(FULL, 700, 400, 0.3, 103.5)
            tracer.add(FULL, 900, None, 0.3, 103.5)
            self.assertTrue(line.startswith("turn 1: 3.50 s"))
            rows = [json.loads(x) for x in path.read_text().splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["steps"]["total"], 3.5)
            summary = tracer.summary()
            self.assertIn("2 replies", summary)
            self.assertIn("decide", summary)
            self.assertIn("line", summary)

    def test_empty_summary(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("no replies", Tracer(pathlib.Path(d) / "t.jsonl").summary())


if __name__ == "__main__":
    unittest.main()
