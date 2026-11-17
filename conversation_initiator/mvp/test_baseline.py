#!/usr/bin/env python3
"""Offline tests for baseline.py. No ROS, no API key, no network.

    python test_baseline.py

The ros4hri_* functions copy the math in ROS4HRI hri_engagement,
engagement_node.py (Apache-2.0), with 3D positions in place of ROS transforms.
The tests check that baseline.py gives the same scores and levels from our
vision fields.
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


def person(d=1.5, x=0.0, yaw=0.0, pitch=0.5, face=True, pid=1):
    return {"id": pid, "distance_m": d, "image_x": x, "face_visible": face,
            "head_yaw": yaw if face else None, "head_pitch": pitch if face else None}


def vision(*people, fresh=True):
    return {"people": list(people), "sensor_status": {"orientation_fresh": fresh}}


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

    def test_farther_than_max_distance_is_a_minus_one_sample(self):
        self.assertIsNone(ros4hri_score((0, 0, 4.2), (4.2, 0, 0)))
        self.assertEqual(b.engagement_score(person(d=4.2), CFG), 0.0)

    def test_perfect_gaze_is_engaged_only_inside_about_2_76_m(self):
        self.assertGreater(b.engagement_score(person(d=2.7), CFG), 0.5)
        self.assertLess(b.engagement_score(person(d=2.8), CFG), 0.5)


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
    """trigger = "level": greet when the ROS4HRI level is engaged."""

    def setUp(self):
        self.base = b.Baseline(b.BaselineConfig(trigger="level"))
        self.t = 0.0

    def feed(self, seconds, *people, fresh=True):
        for _ in range(int(seconds * 10)):
            self.t += 0.1
            self.base.update(vision(*people, fresh=fresh), self.t)

    def decide(self, **overrides):
        return self.base.decide(base_ctx(t=self.t, **overrides), 1)[0]

    def test_greets_once_when_a_person_looks_then_waits_until_they_look_away(self):
        self.feed(1.5, person())
        self.assertEqual(self.decide(), "greet")
        self.base.greeted(1)
        self.feed(3.0, person())
        self.assertEqual(self.decide(), "remain_silent")
        self.feed(3.0, person(yaw=0.5))  # head turned about 51 degrees
        self.assertEqual(self.base.level(1), b.DISENGAGED)
        # Old -1 samples are still in the 2 s window, so it takes 1.6 s, not 1.2 s.
        self.feed(1.5, person())
        self.assertEqual(self.decide(), "remain_silent")
        self.feed(0.1, person())
        self.assertEqual(self.decide(), "greet")

    def test_silent_for_someone_who_does_not_look(self):
        for p in (person(yaw=0.5), person(pitch=0.9), person(face=False), person(d=3.2)):
            self.setUp()
            self.feed(3.0, p)
            self.assertEqual(self.decide(), "remain_silent", p)

    def test_a_glance_while_walking_past_is_not_enough(self):
        self.feed(1.0, person(yaw=0.6))
        self.feed(0.4, person())
        self.feed(1.0, person(yaw=0.6))
        self.assertNotEqual(self.base.level(1), b.ENGAGED)
        self.assertEqual(self.decide(), "remain_silent")

    def test_replies_when_the_person_speaks_and_never_greets_in_a_conversation(self):
        self.feed(2.0, person())
        speech = {"detected": True, "partial_transcript": "where is the lab", "syntactically_complete": True}
        self.assertEqual(self.decide(target={"speech": speech}), "respond")
        self.assertEqual(self.decide(conversation=[{"speaker": "person", "text": "hi"}]), "remain_silent")

    def test_no_person_is_silent(self):
        self.assertEqual(self.base.decide({"target": None}, None)[0], "remain_silent")

    def test_stale_orientation_adds_no_sample(self):
        self.feed(2.0, person(), fresh=False)
        self.assertEqual(self.base.level(1), b.UNKNOWN)

    def test_by_default_the_level_stays_when_the_face_goes_as_in_ros4hri(self):
        self.feed(2.0, person())
        self.feed(3.0, person(face=False))
        self.assertEqual(self.base.level(1), b.ENGAGED)

    def test_away_mode_counts_no_face_as_not_looking(self):
        self.base = b.Baseline(b.BaselineConfig(no_face="away"))
        self.feed(2.0, person())
        self.feed(3.0, person(face=False))
        self.assertEqual(self.base.level(1), b.DISENGAGED)

    def test_a_person_out_of_view_is_forgotten(self):
        self.feed(2.0, person())
        self.feed(6.0)
        self.assertEqual(self.base.level(1), b.UNKNOWN)


class MomentTrigger(Decisions):
    """trigger = "moment" (the default): greet at the first sample with S > 0.5."""

    def setUp(self):
        self.base = b.Baseline()
        self.t = 0.0

    def test_greets_after_one_facing_sample(self):
        self.feed(0.1, person())
        self.assertEqual(self.decide(), "greet")

    def test_greets_once_then_again_only_after_disengaged_and_a_new_look(self):
        self.feed(0.1, person())
        self.assertEqual(self.decide(), "greet")
        self.base.greeted(1)
        self.feed(3.0, person())
        self.assertEqual(self.decide(), "remain_silent")
        self.feed(3.0, person(yaw=0.5))
        self.assertEqual(self.base.level(1), b.DISENGAGED)
        self.assertEqual(self.decide(), "remain_silent")
        self.feed(0.1, person())
        self.assertEqual(self.decide(), "greet")
        self.base.greeted(1)
        self.feed(1.0, person())
        self.assertEqual(self.decide(), "remain_silent")

    def test_one_glance_is_enough(self):
        self.feed(0.1, person())
        self.feed(2.0, person(yaw=0.6))
        self.assertEqual(self.decide(), "greet")

    def test_greets_once_when_a_person_looks_then_waits_until_they_look_away(self):
        self.skipTest("covered by test_greets_once_then_again_only_after_disengaged_and_a_new_look")

    def test_a_glance_while_walking_past_is_not_enough(self):
        self.skipTest("with trigger = moment one glance is enough: see test_one_glance_is_enough")


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

    def test_no_line_when_the_robot_is_talking(self):
        r = mvp.baseline_result(base_ctx(robot={"is_speaking": True}), "greet", {}, 0.1)
        self.assertIsNone(r.speech)


if __name__ == "__main__":
    unittest.main()
