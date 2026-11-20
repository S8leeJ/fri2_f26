#!/usr/bin/env python3
"""Offline tests for baseline.py. No ROS, no API key, no network.

    python test_baseline.py

ros4hri_levels copies compute_engagement in ROS4HRI hri_engagement,
engagement_node.py (Apache-2.0). The tests check Shi et al.'s participation
zones, that the levels match ROS4HRI, and that the baseline greets and replies
as Hriscu et al. describe.
"""

from __future__ import annotations

import random
import unittest
from unittest import mock

import baseline as b
import mvp
from test_gate import base_ctx

CFG = b.BaselineConfig()


def ros4hri_levels(samples, size):
    """compute_engagement after each sample."""
    history, level, out = [], b.UNKNOWN, []
    for s in samples:
        history.append(s)
        if len(history) < int(0.5 * size):
            out.append(level)
            continue
        history = history[-size:]
        v = sum(history) / len(history)
        nxt = b.UNKNOWN
        if level == b.UNKNOWN:
            nxt = b.DISENGAGED
        elif level == b.DISENGAGED:
            if v > -0.4:
                nxt = b.ENGAGING
        elif level == b.ENGAGING:
            if v < -0.6:
                nxt = b.DISENGAGED
            elif v > 0.5:
                nxt = b.ENGAGED
        elif level == b.ENGAGED:
            if v < 0.4:
                nxt = b.DISENGAGING
        elif level == b.DISENGAGING:
            if v > 0.6:
                nxt = b.ENGAGED
            elif v < -0.5:
                nxt = b.DISENGAGED
        if nxt != b.UNKNOWN and nxt != level:
            level = nxt
        out.append(level)
    return out


SIDEWAYS = 90.0


def person(d=1.5, side=0.0, head=0.0, body=0.0, face=True, pid=1):
    """The vision fields the baseline reads. d: floor distance (m). side: angle from the
    robot's forward line. head, body: angle between where they point and the line to the camera."""
    return {"id": pid, "floor_distance_m": d, "side_deg": side, "face_visible": face,
            "head_angle_deg": head if face else None, "body_angle_deg": body}


def vision(*people):
    return {"people": list(people), "sensor_status": {"orientation_fresh": True}}


class ShiZones(unittest.TestCase):
    def part(self, cfg=CFG, **kw):
        return b.participating(person(**kw), cfg)

    def test_head_cone_is_30_degrees(self):
        self.assertTrue(self.part(head=25, body=SIDEWAYS))
        self.assertFalse(self.part(head=35, body=SIDEWAYS))

    def test_body_front_zone_is_60_degrees_within_2_m_as_in_shi(self):
        self.assertTrue(self.part(head=50, body=55, d=1.8))
        self.assertFalse(self.part(head=50, body=65, d=1.8))
        self.assertFalse(self.part(head=50, body=0, d=2.2))
        self.assertFalse(self.part(cfg=b.BaselineConfig(body_zone=False), head=50, body=0, d=1.8))

    def test_gaze_zones_reach_2_5_m_only_near_the_middle_of_the_view(self):
        self.assertTrue(self.part(d=2.3, side=0, body=SIDEWAYS))
        self.assertFalse(self.part(d=2.3, side=-40, body=SIDEWAYS))
        self.assertTrue(self.part(d=1.8, side=-40, body=SIDEWAYS))
        self.assertFalse(self.part(d=2.6, side=0))

    def test_head_down_at_a_phone_counts_only_through_the_body_zone(self):
        self.assertFalse(self.part(head=50, body=SIDEWAYS))
        self.assertTrue(self.part(head=50, body=10))
        self.assertFalse(self.part(cfg=b.BaselineConfig(body_zone=False), head=50, body=10))

    def test_no_body_angle_uses_the_head_only(self):
        self.assertTrue(self.part(head=10, body=None))
        self.assertFalse(self.part(head=50, body=None))

    def test_nothing_measured_is_no_sample(self):
        for p in ({**person(), "face_visible": None},
                  {**person(), "side_deg": None}, {**person(), "floor_distance_m": None}):
            self.assertIsNone(b.participating(p, CFG), p)

    def test_a_face_in_profile_is_not_in_the_gaze_cone(self):
        profile = {**person(body=SIDEWAYS), "head_angle_deg": None}
        self.assertFalse(b.participating(profile, CFG))
        facing_body = {**person(body=10.0), "head_angle_deg": None}
        self.assertTrue(b.participating(facing_body, CFG))  # Shi's body front zone

    def test_looking_aside_in_profile_disengages_then_looking_back_greets_again(self):
        base = b.Baseline()
        profile = {**person(body=SIDEWAYS), "head_angle_deg": None}
        acts = []
        for p, seconds in ((person(), 2.0), (profile, 3.0), (person(), 2.0)):
            for _ in range(int(seconds * 10)):
                acts += [a for a, _, _ in base.step(vision(p), None) if a != "remain_silent"]
        self.assertEqual(acts, ["greet", "greet"])

    def test_no_face_seen_is_not_participating(self):
        self.assertFalse(b.participating(person(face=False), CFG))


class LevelsMatchRos4hri(unittest.TestCase):
    def test_same_levels_for_random_samples(self):
        rng = random.Random(0)
        for size in (20, 100):
            for _ in range(50):
                p = rng.random()
                samples = [1 if rng.random() < p else -1 for _ in range(300)]
                e = b.Engagement(size)
                self.assertEqual([e.add(s) for s in samples], ros4hri_levels(samples, size))

    def test_looking_for_two_seconds_becomes_engaged(self):
        e = b.Engagement(20)
        levels = [e.add(1) for _ in range(12)]
        self.assertEqual(levels[9:12], [b.DISENGAGED, b.ENGAGING, b.ENGAGED])


AWAY = dict(head=50, body=SIDEWAYS)


class Decisions(unittest.TestCase):
    def setUp(self):
        self.base = b.Baseline()

    def feed(self, seconds, *people, audio=None):
        """Messages at 10 Hz. Returns the speaking decisions, with the message number."""
        out = []
        for i in range(int(round(seconds * 10))):
            for action, pid, _ in self.base.step(vision(*people), audio):
                if action != "remain_silent":
                    out.append((i, action, pid))
        return out

    def test_greets_once_when_the_level_becomes_engaged(self):
        self.assertEqual(self.feed(1.1, person()), [])
        self.assertEqual(self.feed(0.1, person()), [(0, "greet", 1)])
        self.assertEqual(self.feed(5.0, person()), [])

    def test_greets_again_only_after_disengaged(self):
        self.feed(3.0, person())
        self.assertEqual(self.feed(1.5, person(**AWAY)), [])
        self.assertEqual(self.base.level(1), b.DISENGAGING)
        self.feed(0.1, person(**AWAY))
        self.assertEqual(self.base.level(1), b.DISENGAGED)
        self.assertEqual([a for _, a, _ in self.feed(3.0, person())], ["greet"])

    def test_silent_for_someone_who_does_not_take_part(self):
        for p in (person(**AWAY), person(face=False), person(d=2.8)):
            self.setUp()
            self.assertEqual(self.feed(5.0, p), [], p)

    def test_a_short_glance_while_walking_past_is_not_enough(self):
        self.feed(1.0, person(**AWAY))
        self.feed(0.4, person())
        self.assertEqual(self.feed(1.0, person(**AWAY)), [])

    def test_each_person_is_greeted_on_their_own(self):
        greets = self.feed(2.0, person(pid=1), person(pid=2, side=15))
        self.assertEqual(sorted(pid for _, _, pid in greets), [1, 2])

    def test_old_vision_adds_no_sample(self):
        for _ in range(30):
            self.base.step(None, None)
        self.assertEqual(self.base.level(1), b.UNKNOWN)

    def test_turning_the_back_then_around_greets_again(self):
        self.assertEqual([a for _, a, _ in self.feed(2.0, person())], ["greet"])
        self.assertEqual(self.feed(5.0, person(face=False)), [])
        self.assertEqual(self.base.level(1), b.DISENGAGED)
        self.assertEqual([a for _, a, _ in self.feed(2.0, person())], ["greet"])

    def test_orientation_not_measured_keeps_the_level(self):
        self.feed(2.0, person())
        self.feed(3.0, {**person(), "face_visible": None, "head_angle_deg": None})
        self.assertEqual(self.base.level(1), b.ENGAGED)

    def test_replies_once_to_each_new_sentence(self):
        self.feed(2.0, person())
        said = {"stamp": 100.0, "transcript": "where is the lab", "transcript_age_s": 0.2}
        self.assertEqual(self.base.step(vision(person()), said), [("respond", 1, "person spoke")])
        again = {**said, "stamp": 101.0, "transcript_age_s": 1.2}
        self.assertEqual(self.base.step(vision(person()), again), [])
        new = {"stamp": 105.0, "transcript": "thanks", "transcript_age_s": 0.3}
        self.assertEqual([a for a, _, _ in self.base.step(vision(person()), new)], ["respond"])

    def test_no_reply_when_nobody_in_view_is_engaged(self):
        said = {"stamp": 100.0, "transcript": "hello", "transcript_age_s": 0.2}
        self.assertEqual(self.base.step(None, said), [("remain_silent", None, "speech, but nobody engaged")])

    def test_two_people_with_their_backs_turned_get_no_reply(self):
        self.feed(2.0, person(pid=1), person(pid=2, side=15))
        self.feed(3.0, person(pid=1, face=False), person(pid=2, side=15, face=False))
        said = {"stamp": 100.0, "transcript": "did you see that", "transcript_age_s": 0.2}
        actions = [a for a, _, _ in self.base.step(vision(person(pid=1, face=False),
                                                          person(pid=2, side=15, face=False)), said)]
        self.assertEqual(actions, ["remain_silent"])

    def test_an_engaged_person_who_left_the_view_does_not_count(self):
        self.feed(2.0, person())
        said = {"stamp": 100.0, "transcript": "hello", "transcript_age_s": 0.2}
        self.assertEqual([a for a, _, _ in self.base.step(vision(), said)], ["remain_silent"])

    def test_a_sentence_from_before_the_start_gets_no_reply(self):
        old = {"stamp": 100.0, "transcript": "hello", "transcript_age_s": 20.0}
        self.feed(2.0, person())
        self.assertEqual(self.base.step(vision(person()), old), [])

    def test_a_transcript_with_no_words_is_not_speech(self):
        for text in (".", "...", " ", "?!"):
            noise = {"stamp": 100.0, "transcript": text, "transcript_age_s": 0.2}
            self.assertEqual(b.Baseline().step(None, noise), [], text)

    def test_level_changes_are_logged_as_silent(self):
        actions = [a for _ in range(12) for a, _, _ in self.base.step(vision(person()), None)]
        self.assertEqual(actions, ["remain_silent", "remain_silent", "greet"])
        snap = self.base.snapshot(1)
        self.assertEqual((snap["level"], snap["participating"], snap["greeted"]), (b.ENGAGED, True, True))


class Lines(unittest.TestCase):
    def test_greeting_is_the_fixed_line_and_reply_uses_the_writers(self):
        r = mvp.baseline_result(base_ctx(), "greet", {}, 0.1)
        self.assertEqual(r.speech.text, mvp.fixed_greeting(base_ctx()).text)
        speech = {"detected": True, "partial_transcript": "hi", "syntactically_complete": True}
        ctx = base_ctx(target={"speech": speech})
        with mock.patch.object(mvp, "_write_line", return_value=("line", 5.0, None)) as write, \
                mock.patch.object(mvp, "reply_writers", return_value=["w"]):
            r = mvp.baseline_result(ctx, "respond", {}, 0.1)
        write.assert_called_once_with(["w"], ctx, {"action": "respond"})
        self.assertEqual((r.speech, r.ms2), ("line", 5.0))

    def test_no_post_filter_the_decision_is_final(self):
        r = mvp.baseline_result(base_ctx(robot={"is_speaking": True}), "greet", {}, 0.1)
        self.assertIsNotNone(r.speech)
        self.assertIsNone(mvp.baseline_result(base_ctx(), "remain_silent", {}, 0.1).speech)


if __name__ == "__main__":
    unittest.main()
