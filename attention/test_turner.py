#!/usr/bin/env python3
"""Offline tests for turner.py. No ROS, no robot.

    python3 test_turner.py
"""

import math
import unittest

from turner import Turner, wrap


def run(turner, t, engaged, bearing, yaw):
    return turner.update(t, engaged, bearing, yaw)


class RuleTests(unittest.TestCase):
    def test_no_turn_when_not_engaged(self):
        t = Turner()
        self.assertEqual(run(t, 0.0, False, 30.0, 0.0), (0.0, None))

    def test_small_offsets_never_turn(self):
        t = Turner()
        for i in range(100):
            omega, _ = run(t, i * 0.05, True, 10.0, 0.0)
            self.assertEqual(omega, 0.0)

    def test_waits_hold_time_then_turns_toward_the_person(self):
        t = Turner()
        self.assertEqual(run(t, 0.0, True, 20.0, 0.0)[0], 0.0)
        self.assertEqual(run(t, 0.5, True, 20.0, 0.0)[0], 0.0)
        omega, note = run(t, 1.0, True, 20.0, 0.0)
        self.assertLess(omega, 0.0)                 # person on the right: turn right
        self.assertIn("turning right", note)
        omega, _ = Turner().update(0.0, True, -20.0, 0.0)
        t2 = Turner()
        run(t2, 0.0, True, -20.0, 0.0)
        self.assertGreater(run(t2, 1.0, True, -20.0, 0.0)[0], 0.0)

    def test_stops_when_centered(self):
        t = Turner()
        run(t, 0.0, True, 20.0, 0.0)
        run(t, 1.0, True, 20.0, 0.0)
        omega, note = run(t, 1.5, True, 3.0, -15.0)
        self.assertEqual(omega, 0.0)
        self.assertIn("centered", note)

    def test_never_past_the_limit(self):
        t = Turner(max_turn_deg=40.0)
        run(t, 0.0, True, 20.0, 0.0)               # home heading is 0
        run(t, 1.0, True, 20.0, 0.0)
        omega, note = run(t, 2.0, True, 20.0, -40.0)
        self.assertEqual(omega, 0.0)
        self.assertIn("limit", note)
        for i in range(50):                        # the person stays far off: still no turn
            self.assertEqual(run(t, 3.0 + i * 0.05, True, 25.0, -40.0)[0], 0.0)
        run(t, 6.0, True, -20.0, -40.0)            # but turning back toward home is allowed
        self.assertGreater(run(t, 7.0, True, -20.0, -40.0)[0], 0.0)

    def test_stops_when_the_person_is_lost(self):
        t = Turner()
        run(t, 0.0, True, 20.0, 0.0)
        run(t, 1.0, True, 20.0, 0.0)
        omega, note = run(t, 1.2, True, None, -2.0)
        self.assertEqual(omega, 0.0)
        self.assertIn("nobody", note)

    def test_stops_without_odometry(self):
        t = Turner()
        run(t, 0.0, True, 20.0, 0.0)
        run(t, 1.0, True, 20.0, 0.0)
        self.assertEqual(run(t, 1.2, True, 20.0, None)[0], 0.0)

    def test_turn_times_out(self):
        t = Turner(move_timeout_s=6.0)
        run(t, 0.0, True, 20.0, 0.0)
        run(t, 1.0, True, 20.0, 0.0)
        omega, note = run(t, 7.5, True, 20.0, -10.0)
        self.assertEqual(omega, 0.0)
        self.assertIn("too long", note)

    def test_turns_back_home_when_the_conversation_ends(self):
        t = Turner()
        run(t, 0.0, True, 20.0, 0.0)
        run(t, 1.0, True, 20.0, 0.0)
        run(t, 3.0, True, 2.0, -25.0)              # centered after turning right 25 deg
        omega, note = run(t, 4.0, False, None, -25.0)
        self.assertGreater(omega, 0.0)             # turn left to go back
        self.assertIn("turning back", note)
        omega, note = run(t, 6.0, False, None, -1.0)
        self.assertEqual(omega, 0.0)
        self.assertIn("back at the start", note)
        self.assertIsNone(t.home)

    def test_new_conversation_while_returning_keeps_the_first_home(self):
        t = Turner()
        run(t, 0.0, True, 20.0, 10.0)              # home heading is 10
        run(t, 1.0, True, 20.0, 10.0)
        run(t, 3.0, True, 2.0, -15.0)
        run(t, 4.0, False, None, -15.0)            # returning
        run(t, 4.5, True, None, -12.0)             # someone engages again
        self.assertEqual(t.home, 10.0)

    def test_every_conversation_returns_to_the_first_rest_heading(self):
        t = Turner()
        run(t, 0.0, True, 2.0, 0.0)                # first conversation: rest heading is 0
        run(t, 1.0, False, None, 1.5)              # ended 1.5 deg off, within 2: counts as home
        run(t, 2.0, True, 2.0, 1.5)                # second conversation
        self.assertEqual(t.home, 0.0)

    def test_return_times_out(self):
        t = Turner(return_timeout_s=15.0)
        run(t, 0.0, True, 20.0, 0.0)
        run(t, 1.0, True, 20.0, 0.0)
        run(t, 3.0, True, 2.0, -25.0)
        run(t, 4.0, False, None, -25.0)
        omega, note = run(t, 20.0, False, None, -25.0)
        self.assertEqual(omega, 0.0)
        self.assertIn("could not get back", note)

    def test_wrap(self):
        self.assertAlmostEqual(wrap(-349.2), 10.8)
        self.assertAlmostEqual(wrap(190.0), -170.0)


class SimulationTests(unittest.TestCase):
    """The robot turns at the speed it commands; the person stands still in the room."""

    def simulate(self, person_deg, seconds_engaged=10.0, rate_factor=2.0):
        t, yaw, dt, now, notes = Turner(), 0.0, 0.05, 0.0, []
        while now < 40.0:
            engaged = now < seconds_engaged
            bearing = wrap(person_deg - (-yaw)) if engaged else None   # yaw left is +, bearing right is +
            omega, note = t.update(now, engaged, bearing, yaw)
            if note:
                notes.append(note)
            yaw += math.degrees(omega * rate_factor) * dt               # flexo turned about 2x the command
            now += dt
        return yaw, bearing, notes, t

    def test_centers_then_returns(self):
        yaw, _, notes, t = self.simulate(person_deg=25.0)
        self.assertTrue(any("centered" in n for n in notes))
        self.assertTrue(any("back at the start" in n for n in notes))
        self.assertLess(abs(yaw), 2.5)
        self.assertIsNone(t.home)

    def test_far_off_person_stops_at_the_limit(self):
        t, yaw, dt, now = Turner(max_turn_deg=40.0), 0.0, 0.05, 0.0
        while now < 12.0:
            omega, _ = t.update(now, True, wrap(70.0 + yaw), yaw)
            yaw += math.degrees(omega * 2.0) * dt
            now += dt
        self.assertLessEqual(abs(yaw), 40.0 + 1.5)


if __name__ == "__main__":
    unittest.main()
