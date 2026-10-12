#!/usr/bin/env python3
"""Offline tests for fusion_adapter. No ROS, no API key, no network.

    python test_fusion_adapter.py
"""

from __future__ import annotations

import unittest

from context import validate
from fusion_adapter import (
    LOST_TARGET_S,
    NO_REPLY_S,
    Memory,
    apply_result,
    consume_pending,
    fusion_to_context,
)

T0 = 1791447000.0


def audio(stamp=T0, transcript="", age=None, complete=None, **extra):
    msg = {
        "stamp": stamp, "noise_floor_db": -42.0, "noise_level": "moderate",
        "speech_snr_db": None, "speech_now": False, "speech_ratio_10s": 0.1,
        "seconds_since_speech": 4.0, "transcript": transcript, "transcript_age_s": age,
        "syntactically_complete": complete, "tone": None, "engaged": False,
        "robot_speaking": False,
    }
    msg.update(extra)
    return msg


def person(pid, distance, orientation="facing_robot", direction="stationary", dwell=3.0):
    return {"id": pid, "confidence": 0.9, "distance_m": distance, "direction": direction,
            "dwell_time_s": dwell, "orientation": orientation,
            "gaze": "toward_robot" if orientation == "facing_robot" else "unknown",
            "face_visible": orientation == "facing_robot"}


def wrapper(people=(), audio_msg=None, t=T0, vision_age=0.1, audio_age=0.4, orientation_fresh=True):
    vision = {"person_count": len(people), "people": list(people),
              "sensor_status": {"depth_fresh": True, "orientation_fresh": orientation_fresh}}
    return {"t": t, "audio": audio_msg if audio_msg is not None else audio(stamp=t),
            "audio_age_s": audio_age, "vision": vision, "vision_age_s": vision_age}


class AdapterTests(unittest.TestCase):
    def build(self, msg, mem=None, now=T0):
        mem = mem or Memory()
        ctx = fusion_to_context(msg, mem, now)
        validate(ctx)
        return ctx, mem

    def test_nobody_gives_null_target(self):
        ctx, _ = self.build(wrapper())
        self.assertIsNone(ctx["target"])
        self.assertEqual(ctx["bystanders"], [])
        self.assertEqual(ctx["ambient"]["noise_level"], "moderate")

    def test_nearest_is_target_rest_are_bystanders(self):
        ctx, mem = self.build(wrapper([person(1, 3.0), person(2, 1.2, "sideways")]))
        self.assertEqual(ctx["target"]["distance_m"], 1.2)
        self.assertFalse(ctx["target"]["facing_robot"])
        self.assertEqual(mem.target_id, 2)
        self.assertEqual(ctx["bystanders"], [{"distance_m": 3.0, "facing_robot": True}])

    def test_people_without_distance_are_skipped(self):
        ctx, _ = self.build(wrapper([person(1, None)]))
        self.assertIsNone(ctx["target"])

    def test_target_is_sticky(self):
        mem = Memory()
        self.build(wrapper([person(1, 1.5)]), mem)
        ctx, _ = self.build(wrapper([person(1, 1.5), person(2, 1.3)]), mem, T0 + 1)
        self.assertEqual(mem.target_id, 1)
        ctx, _ = self.build(wrapper([person(1, 2.5), person(2, 1.3)]), mem, T0 + 2)
        self.assertEqual(mem.target_id, 2)

    def test_direction_and_dwell_map(self):
        ctx, _ = self.build(wrapper([person(1, 2.0, direction="receding", dwell=7.5)]))
        self.assertEqual(ctx["target"]["motion"], "leaving")
        self.assertEqual(ctx["target"]["dwell_s"], 7.5)
        ctx, _ = self.build(wrapper([person(1, 2.0, direction="unknown")]))
        self.assertNotIn("motion", ctx["target"])

    def test_gaze_accumulates_then_resets(self):
        mem = Memory()
        ctx, _ = self.build(wrapper([person(1, 2.0)]), mem, T0)
        self.assertEqual(ctx["target"]["gaze_at_robot_s"], 0.0)
        ctx, _ = self.build(wrapper([person(1, 2.0)]), mem, T0 + 2.5)
        self.assertEqual(ctx["target"]["gaze_at_robot_s"], 2.5)
        ctx, _ = self.build(wrapper([person(1, 2.0, "likely_facing_away")]), mem, T0 + 3)
        self.assertEqual(ctx["target"]["gaze_at_robot_s"], 0.0)

    def test_stale_orientation_omits_gaze(self):
        ctx, _ = self.build(wrapper([person(1, 2.0)], orientation_fresh=False))
        self.assertNotIn("gaze_at_robot_s", ctx["target"])

    def test_stale_vision_gives_null_target(self):
        ctx, _ = self.build(wrapper([person(1, 2.0)], vision_age=5.0))
        self.assertIsNone(ctx["target"])

    def test_stale_audio_gives_empty_ambient(self):
        ctx, _ = self.build(wrapper([person(1, 2.0)], audio_age=10.0))
        self.assertEqual(ctx["ambient"], {})

    def test_transcript_used_once(self):
        mem = Memory()
        said = audio(stamp=T0, transcript="Where is the elevator?", age=0.5, complete=True)
        ctx, _ = self.build(wrapper([person(1, 1.5)], said), mem, T0)
        self.assertEqual(ctx["target"]["speech"]["partial_transcript"], "Where is the elevator?")
        self.assertTrue(ctx["target"]["speech"]["syntactically_complete"])
        consume_pending(mem)
        # The audio node repeats the same transcript every second.
        again = audio(stamp=T0 + 1, transcript="Where is the elevator?", age=1.5, complete=True)
        ctx, _ = self.build(wrapper([person(1, 1.5)], again, t=T0 + 1), mem, T0 + 1)
        self.assertNotIn("speech", ctx["target"])
        self.assertEqual([c["speaker"] for c in ctx["conversation"]], ["person"])

    def test_pending_transcript_survives_until_consumed(self):
        mem = Memory()
        said = audio(stamp=T0, transcript="hi", age=0.2, complete=True)
        self.build(wrapper([person(1, 1.5)], said), mem, T0)
        later = audio(stamp=T0 + 1, transcript="hi", age=1.2, complete=True)
        ctx, _ = self.build(wrapper([person(1, 1.5)], later, t=T0 + 1), mem, T0 + 1)
        self.assertEqual(ctx["target"]["speech"]["partial_transcript"], "hi")

    def test_old_transcript_at_start_is_ignored(self):
        old = audio(stamp=T0, transcript="earlier talk", age=20.0, complete=True)
        ctx, _ = self.build(wrapper([person(1, 1.5)], old))
        self.assertNotIn("speech", ctx["target"])

    def test_robot_line_and_no_reply(self):
        mem = Memory()
        self.build(wrapper([person(1, 1.5)]), mem, T0)
        apply_result(mem, "greet", "R5 facing", "Hi there!", T0)
        ctx, _ = self.build(wrapper([person(1, 1.5)], t=T0 + 2), mem, T0 + 2)
        self.assertTrue(ctx["robot"]["engaged"])
        self.assertEqual(ctx["robot"]["last_spoke_s_ago"], 2.0)
        self.assertEqual(ctx["recent_decisions"][0]["action"], "greet")
        self.assertEqual(ctx["conversation"][-1], {"speaker": "robot", "text": "Hi there!", "s_ago": 2.0})
        ctx, _ = self.build(wrapper([person(1, 1.5)]), mem, T0 + NO_REPLY_S + 1)
        self.assertEqual(ctx["robot"]["consecutive_no_response"], 1)

    def test_reply_resets_no_response(self):
        mem = Memory(no_response=1)
        self.build(wrapper([person(1, 1.5)]), mem, T0)
        said = audio(stamp=T0 + 1, transcript="yes?", age=0.3, complete=True)
        ctx, _ = self.build(wrapper([person(1, 1.5)], said, t=T0 + 1), mem, T0 + 1)
        self.assertEqual(ctx["robot"]["consecutive_no_response"], 0)

    def test_new_person_ends_interaction(self):
        mem = Memory()
        self.build(wrapper([person(1, 1.5)]), mem, T0)
        apply_result(mem, "greet", None, "Hi!", T0)
        ctx, _ = self.build(wrapper([person(7, 1.5)]), mem, T0 + 1)
        self.assertFalse(ctx["robot"]["engaged"])
        self.assertEqual(ctx["conversation"], [])

    def test_lost_target_ends_interaction_after_timeout(self):
        mem = Memory()
        self.build(wrapper([person(1, 1.5)]), mem, T0)
        apply_result(mem, "greet", None, "Hi!", T0)
        ctx, _ = self.build(wrapper([]), mem, T0 + 2)
        self.assertTrue(ctx["robot"]["engaged"])
        ctx, _ = self.build(wrapper([]), mem, T0 + LOST_TARGET_S + 1)
        self.assertFalse(ctx["robot"]["engaged"])

    def test_missing_sources_still_valid(self):
        msg = {"t": T0, "audio": None, "audio_age_s": None, "vision": None, "vision_age_s": None}
        ctx, _ = self.build(msg)
        self.assertIsNone(ctx["target"])


if __name__ == "__main__":
    unittest.main()
