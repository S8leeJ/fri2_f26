#!/usr/bin/env python3
"""Offline tests for bench_decide.py. No API key, no network.

    python test_bench_decide.py
"""

from __future__ import annotations

import json
import pathlib
import statistics
import tempfile
import unittest

import bench_decide as bench
import mvp
from test_gate import base_ctx


def fake_ask(times):
    """An ask() that returns the next time for each provider, or raises it."""
    calls = []

    def ask(provider, client, model, system, user, schema, max_tokens):
        calls.append((provider, json.loads(user)["t"], system, schema))
        ms = times[provider].pop(0)
        if isinstance(ms, Exception):
            raise ms
        d = mvp.Decision6(rubric=mvp.Rubric(invitation=3, interruption_cost=3, urgency=1, redundancy=1,
                                            ambient_fit=3, addressivity=3),
                          action="wait", category="insufficient_evidence", rule_fired="",
                          confidence=0.5, recheck_in_ms=0)
        return d, ms, 40 if provider == "groq" else None

    ask.calls = calls
    return ask


SCENES = [("a", base_ctx(t=1.0)), ("b", base_ctx(t=2.0)), ("c", base_ctx(t=3.0))]


class Run(unittest.TestCase):
    def run_bench(self, times, n):
        ask = fake_ask(times)
        rows = bench.run(["jev", "groq"], {"jev": None, "groq": None},
                         {"jev": "jev-latest", "groq": "g"}, SCENES, n, ask, show=False)
        return rows, ask.calls

    def test_warm_up_is_not_counted_and_the_order_alternates(self):
        rows, calls = self.run_bench({"jev": [999, 1, 2, 3, 4], "groq": [999, 5, 6, 7, 8]}, 4)
        self.assertEqual([c[0] for c in calls],
                         ["jev", "groq", "jev", "groq", "groq", "jev", "jev", "groq", "groq", "jev"])
        self.assertNotIn(999, [r["ms"] for r in rows])
        self.assertEqual([r["ms"] for r in rows if r["provider"] == "jev"], [1, 2, 3, 4])

    def test_both_providers_get_the_same_scenes_and_the_no_rules_prompt(self):
        _, calls = self.run_bench({"jev": [0] * 5, "groq": [0] * 5}, 4)
        timed = calls[2:]
        self.assertEqual(sorted(c[1] for c in timed if c[0] == "jev"),
                         sorted(c[1] for c in timed if c[0] == "groq"))
        self.assertEqual([c[1] for c in timed if c[0] == "jev"], [1.0, 2.0, 3.0, 1.0])
        self.assertTrue(all(c[2] == mvp.SYSTEM_6_SCENE and c[3] is mvp.Decision6 for c in calls))

    def test_a_failed_call_is_counted_and_has_no_time(self):
        rows, _ = self.run_bench({"jev": [0, 100, TimeoutError("read timeout"), 300],
                                  "groq": [0, 500, 2500, 700]}, 3)
        jev, groq = bench.summarize(rows, "jev"), bench.summarize(rows, "groq")
        self.assertEqual((jev["n"], jev["failed"], jev["median_ms"]), (2, 1, 200))
        self.assertTrue(next(r for r in rows if r["ms"] is None)["error"].startswith("timeout"))
        self.assertEqual((groq["n"], groq["over_2s"], groq["median_reasoning_tokens"]), (3, 1, 40))


class Summary(unittest.TestCase):
    def test_median_and_sample_sd(self):
        ms = [180.0, 200.0, 210.0, 260.0]
        rows = [{"provider": "jev", "ms": m} for m in ms]
        s = bench.summarize(rows, "jev")
        self.assertEqual(s["median_ms"], 205.0)
        self.assertAlmostEqual(s["sd_ms"], statistics.stdev(ms))
        self.assertEqual((s["min_ms"], s["max_ms"], s["failed"]), (180.0, 260.0, 0))

    def test_one_call_has_no_sd(self):
        self.assertIsNone(bench.summarize([{"provider": "jev", "ms": 5.0}], "jev")["sd_ms"])

    def test_report_has_a_paper_line(self):
        rows = [{"provider": "jev", "ms": m} for m in (200.0, 220.0)]
        rows += [{"provider": "groq", "ms": m} for m in (600.0, 800.0)]
        text = bench.report([bench.summarize(rows, "jev"), bench.summarize(rows, "groq")],
                            {"jev": "jev-latest", "groq": "openai/gpt-oss-120b"}, 2, "vignettes")
        self.assertIn("Jev took a median of 210 ms (SD 14 ms, n = 2)", text)
        self.assertIn("Groq (openai/gpt-oss-120b) took a median of 700 ms (SD 141 ms, n = 2)", text)


class Scenes(unittest.TestCase):
    def test_vignettes_load(self):
        scenes = bench.load_scenes("vignettes")
        self.assertGreaterEqual(len(scenes), 10)
        self.assertTrue(all("schema_version" in ctx for _, ctx in scenes))

    def test_live_scenes_come_from_the_newest_file_and_need_a_person(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = pathlib.Path(tmp)
            (logs / "2026-11-16.jsonl").write_text(json.dumps({"context": base_ctx(t=9.0)}) + "\n")
            (logs / "2026-11-17.jsonl").write_text("\n".join([
                json.dumps({"run_start": "x", "run": 1}),
                json.dumps({"run": 1, "context": {**base_ctx(t=1.0), "target": None}}),
                json.dumps({"run": 1, "context": base_ctx(t=2.0)}),
                json.dumps({"run": 1, "t": 3.0, "trace": {}}),
            ]) + "\n")
            scenes = bench.load_scenes("logs", logs)
        self.assertEqual([(name, ctx["t"]) for name, ctx in scenes], [("2026-11-17.jsonl:3", 2.0)])


def fusion_msg(t, people):
    return json.dumps({
        "t": t, "audio": {"stamp": t, "noise_floor_db": -55, "noise_level": "quiet", "speech_now": False},
        "audio_age_s": 0.1, "vision_age_s": 0.1,
        "vision": {"people": people, "sensor_status": {"depth_fresh": True, "orientation_fresh": True}}})


PERSON = {"id": 7, "distance_m": 1.4, "direction": "stationary", "dwell_time_s": 3.0, "image_x": 0.1,
          "orientation": "facing_robot", "gaze": "toward_robot", "face_visible": True,
          "head_yaw": 0.0, "head_pitch": 0.5}


class Live(unittest.TestCase):
    def test_a_scene_needs_a_person_and_a_recent_message(self):
        src = bench.LiveScenes()
        self.assertIsNone(src.take(100.0))
        src.on_message(fusion_msg(100.0, []), 100.0)
        self.assertIsNone(src.take(100.1))
        src.on_message(fusion_msg(101.0, [PERSON]), 101.0)
        name, ctx = src.take(101.1)
        self.assertEqual((name, ctx["target"]["distance_m"], ctx["target"]["facing_robot"]),
                         ("live:1", 1.4, True))
        self.assertIsNone(src.take(104.0))
        src.on_message("not json", 104.0)

    def test_gaze_time_builds_up_as_in_live_node(self):
        src = bench.LiveScenes()
        for i in range(21):
            src.on_message(fusion_msg(200.0 + i / 10, [PERSON]), 200.0 + i / 10)
        self.assertEqual(src.take(202.0)[1]["target"]["gaze_at_robot_s"], 2.0)

    def test_at_most_one_scene_each_every_seconds(self):
        src = bench.LiveScenes()
        clock = {"t": 300.0}
        said = []

        def sleep(s):
            clock["t"] += s
            src.on_message(fusion_msg(clock["t"], [PERSON] if clock["t"] >= 301.0 else []), clock["t"])

        gen = bench.live_scenes(src, 1.0, clock=lambda: clock["t"], sleep=sleep, say=said.append)
        times = []
        for _ in range(3):
            next(gen)
            times.append(clock["t"])
        self.assertEqual(len(said), 1)
        self.assertGreaterEqual(times[0], 301.0)
        self.assertTrue(all(b - a >= 1.0 - 1e-9 for a, b in zip(times, times[1:])))

    def test_run_takes_scenes_from_a_generator_and_records_the_person(self):
        src = bench.LiveScenes()
        src.on_message(fusion_msg(400.0, [PERSON]), 400.0)
        gen = iter([src.take(400.0), src.take(400.1), src.take(400.2)])
        ask = fake_ask({"jev": [0, 1, 2], "groq": [0, 3, 4]})
        rows = bench.run(["jev", "groq"], {"jev": None, "groq": None}, {"jev": "j", "groq": "g"},
                         gen, 2, ask, show=False)
        self.assertEqual([r["scene"] for r in rows], ["live:1", "live:1", "live:2", "live:2"])
        self.assertEqual(rows[0]["person"]["distance_m"], 1.4)


class Models(unittest.TestCase):
    def test_groq_model_follows_the_reply_writer(self):
        self.assertEqual(bench.model_for("groq", "x"), "x")
        self.assertEqual(bench.model_for("jev"), mvp.DEFAULT_MODEL["jev"])


if __name__ == "__main__":
    unittest.main()
