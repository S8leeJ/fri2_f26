#!/usr/bin/env python3
"""Offline tests for baseline.py. No ROS, no API key, no network.

    python test_baseline.py

The ros4hri_* functions copy the math in ROS4HRI hri_engagement,
engagement_node.py (Apache-2.0), with 3D positions in place of ROS transforms.
The tests check that baseline.py gives the same scores and levels from our
vision fields, and that it greets and replies as Hriscu et al. describe.
"""

from __future__ import annotations

import math
import random
import unittest
from unittest import mock

import baseline as b
import mvp
from test_gate import base_ctx

CFG = b.BaselineConfig()


def ros4hri_score(robot_in_person, person_in_robot, fov_deg=60.0, max_distance=4.0):
    """assess_engagement. robot_in_person: optical frame (+z forward).
    person_in_robot: robot frame (+x forward). None is a -1 sample for distance."""
    fov = math.radians(fov_deg)
    tx, ty, tz = robot_in_person
    d_ab = math.sqrt(tx ** 2 + ty ** 2 + tz ** 2)
    if d_ab > max_distance:
        return None
    xb, yb, zb = tz, tx, ty
    gaze_ab = 0.0
    if xb > 0:
        gaze_ab = max(0, 1 - (math.sqrt(yb ** 2 + zb ** 2) / (math.tan(fov) * xb)))
    xa, ya, za = person_in_robot
    gaze_ba = 0.0
    log_d_ab = 0.0
    if xa > 0:
        gaze_ba = max(0, 1 - (math.sqrt(ya ** 2 + za ** 2) / (math.tan(fov) * xa)))
        log_d_ab = math.log(-d_ab + max_distance + 1) / math.log(max_distance + 1)
    return min(1, gaze_ab * gaze_ba * log_d_ab)


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


def person(d=1.5, x=0.0, yaw=0.0, pitch=CFG.pitch_ahead, face=True, pid=1):
    return {"id": pid, "distance_m": d, "image_x": x, "face_visible": face,
            "head_yaw": yaw if face else None, "head_pitch": pitch if face else None}


def vision(*people):
    return {"people": list(people), "sensor_status": {"orientation_fresh": True}}


class ScoreMatchesRos4hri(unittest.TestCase):
    def test_same_score_over_a_grid_of_scenes(self):
        for d in (0.6, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 3.9):
            for phi in (0, 10, 25, 40):        # person's angle from the camera axis
                for theta in (0, 10, 20, 35, 55, 70):  # head angle away from the robot
                    p, t = math.radians(phi), math.radians(theta)
                    want = ros4hri_score((d * math.sin(t), 0.0, d * math.cos(t)),
                                         (d * math.cos(p), d * math.sin(p), 0.0))
                    # Vision gives depth along the camera axis, not the straight-line distance.
                    ours = b.engagement_score(
                        person(d=d * math.cos(p), x=math.tan(p), yaw=CFG.k * math.tan(t)), CFG)
                    self.assertAlmostEqual(ours, want, places=9, msg=(d, phi, theta))

    def test_same_score_with_the_head_turned_and_tilted(self):
        for d in (1.0, 2.0, 3.0):
            for turn in (0, 10, 25):
                for tilt in (-20, -5, 0, 10, 20, 35):   # positive: down, as at a phone
                    t1, t2 = math.tan(math.radians(turn)), math.tan(math.radians(tilt))
                    n = math.sqrt(1 + t1 ** 2 + t2 ** 2)
                    # The robot in the head's optical frame: x right, y down, z forward.
                    want = ros4hri_score((d * t1 / n, d * t2 / n, d / n), (d, 0.0, 0.0))
                    ours = b.engagement_score(
                        person(d=d, yaw=CFG.k * t1, pitch=CFG.pitch_ahead + CFG.k_tilt * t2), CFG)
                    self.assertAlmostEqual(ours, want, places=9, msg=(d, turn, tilt))

    def test_farther_than_max_distance_is_a_minus_one_sample(self):
        self.assertIsNone(ros4hri_score((0, 0, 4.2), (4.2, 0, 0)))
        self.assertEqual(b.engagement_score(person(d=4.2), CFG), 0.0)

    def test_perfect_gaze_is_engaged_only_inside_about_2_76_m(self):
        self.assertGreater(b.engagement_score(person(d=2.7), CFG), 0.5)
        self.assertLess(b.engagement_score(person(d=2.8), CFG), 0.5)

    def test_no_face_or_no_head_or_no_position_is_no_sample(self):
        for p in (person(face=False), {**person(), "head_yaw": None}, {**person(), "head_pitch": None},
                  {**person(), "image_x": None}, {**person(), "distance_m": None}):
            self.assertIsNone(b.engagement_score(p, CFG), p)

    def test_tilting_the_head_up_or_down_lowers_the_score_the_same(self):
        ahead = b.engagement_score(person(), CFG)
        down = b.engagement_score(person(pitch=CFG.pitch_ahead + 0.1), CFG)
        up = b.engagement_score(person(pitch=CFG.pitch_ahead - 0.1), CFG)
        self.assertLess(down, ahead)
        self.assertAlmostEqual(down, up)


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
        self.assertEqual(self.feed(1.5, person(yaw=0.5)), [])  # head turned about 51 degrees
        self.assertEqual(self.base.level(1), b.DISENGAGING)
        self.feed(0.1, person(yaw=0.5))
        self.assertEqual(self.base.level(1), b.DISENGAGED)
        greets = self.feed(3.0, person())
        self.assertEqual([a for _, a, _ in greets], ["greet"])

    def test_silent_for_someone_who_does_not_look(self):
        for p in (person(yaw=0.5), person(face=False), person(d=3.2)):
            self.setUp()
            self.assertEqual(self.feed(5.0, p), [], p)

    def test_head_tilted_down_at_a_phone_is_not_greeted(self):
        self.assertEqual(self.feed(5.0, person(pitch=0.95)), [])

    def test_a_short_glance_while_walking_past_is_not_enough(self):
        self.feed(1.0, person(yaw=0.6))
        self.feed(0.4, person())
        self.assertEqual(self.feed(1.0, person(yaw=0.6)), [])

    def test_each_person_is_greeted_on_their_own(self):
        greets = self.feed(2.0, person(pid=1), person(pid=2, x=0.2))
        self.assertEqual(sorted(pid for _, _, pid in greets), [1, 2])

    def test_old_vision_adds_no_sample(self):
        for _ in range(30):
            self.base.step(None, None)
        self.assertEqual(self.base.level(1), b.UNKNOWN)

    def test_no_face_keeps_the_level_as_in_ros4hri(self):
        self.feed(2.0, person())
        self.feed(3.0, person(face=False))
        self.assertEqual(self.base.level(1), b.ENGAGED)

    def test_replies_once_to_each_new_sentence(self):
        said = {"stamp": 100.0, "transcript": "where is the lab", "transcript_age_s": 0.2}
        self.assertEqual(self.base.step(None, said), [("respond", None, "person spoke")])
        again = {**said, "stamp": 101.0, "transcript_age_s": 1.2}
        self.assertEqual(self.base.step(None, again), [])
        new = {"stamp": 105.0, "transcript": "thanks", "transcript_age_s": 0.3}
        self.assertEqual([a for a, _, _ in self.base.step(None, new)], ["respond"])

    def test_a_sentence_from_before_the_start_gets_no_reply(self):
        old = {"stamp": 100.0, "transcript": "hello", "transcript_age_s": 20.0}
        self.assertEqual(self.base.step(None, old), [])

    def test_level_changes_are_logged_as_silent(self):
        actions = [a for _ in range(12) for a, _, _ in self.base.step(vision(person()), None)]
        self.assertEqual(actions, ["remain_silent", "remain_silent", "greet"])


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
