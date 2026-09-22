#!/usr/bin/env python3
"""Offline tests for the gate. No API key, no network.

    python test_gate.py
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import unittest

from context import audio_to_context, validate
from gate import (
    DEFAULTS,
    GateState,
    decide_tick,
    materially_changed,
    note_asked,
    should_ask_llm,
)

VIGNETTES = pathlib.Path(__file__).parent / "vignettes"


def base_ctx(t=0.0, **overrides):
    ctx = {
        "schema_version": "2.0",
        "t": t,
        "target": {
            "distance_m": 2.0,
            "facing_robot": True,
            "gaze_at_robot_s": 1.0,
            "motion": "stationary",
            "in_conversation": False,
            "activity": "idle",
        },
        "ambient": {
            "noise_floor_db": -58.0,
            "noise_level": "quiet",
            "speech_now": False,
        },
        "robot": {
            "is_speaking": False,
            "last_spoke_s_ago": None,
            "consecutive_no_response": 0,
        },
    }
    for key, value in overrides.items():
        if key in ("target", "ambient", "robot") and isinstance(value, dict):
            ctx[key] = {**ctx[key], **value}
        else:
            ctx[key] = value
    return ctx


class GateUnitTests(unittest.TestCase):
    def test_no_person(self):
        state = GateState()
        ok, reason = should_ask_llm(base_ctx(target=None), state)
        self.assertFalse(ok)
        self.assertEqual(reason, "no_person")

    def test_self_speaking(self):
        state = GateState()
        ok, reason = should_ask_llm(base_ctx(robot={"is_speaking": True}), state)
        self.assertFalse(ok)
        self.assertEqual(reason, "self_speaking")

    def test_gave_up(self):
        state = GateState()
        ok, reason = should_ask_llm(
            base_ctx(robot={"consecutive_no_response": 2}), state
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "gave_up")

    def test_first_tick_asks(self):
        state = GateState()
        ok, reason = should_ask_llm(base_ctx(t=0.0), state)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_cooldown_blocks(self):
        state = GateState()
        ctx0 = base_ctx(t=0.0)
        note_asked(state, ctx0)
        ok, reason = should_ask_llm(base_ctx(t=1.0), state)  # < 3s
        self.assertFalse(ok)
        self.assertEqual(reason, "cooldown")

    def test_no_material_change_after_cooldown(self):
        state = GateState()
        ctx0 = base_ctx(t=0.0)
        note_asked(state, ctx0)
        # Same scene, past cooldown → blocked as no_material_change
        ok, reason = should_ask_llm(base_ctx(t=5.0), state)
        self.assertFalse(ok)
        self.assertEqual(reason, "no_material_change")

    def test_material_change_distance_allows(self):
        state = GateState()
        note_asked(state, base_ctx(t=0.0))
        ok, reason = should_ask_llm(
            base_ctx(t=5.0, target={"distance_m": 2.5}), state
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_facing_flip_is_material(self):
        a = base_ctx(target={"facing_robot": True})
        b = base_ctx(target={"facing_robot": False})
        self.assertTrue(materially_changed(b, a))

    def test_motion_change_is_material(self):
        a = base_ctx(target={"motion": "approaching"})
        b = base_ctx(target={"motion": "passing"})
        self.assertTrue(materially_changed(b, a))

    def test_audio_changes_are_material(self):
        base = base_ctx()
        self.assertTrue(materially_changed(base_ctx(ambient={"noise_level": "loud"}), base))
        self.assertTrue(materially_changed(base_ctx(ambient={"noise_floor_db": -50.0}), base))
        self.assertTrue(materially_changed(base_ctx(ambient={"speech_now": True}), base))
        self.assertFalse(materially_changed(base_ctx(ambient={"noise_floor_db": -56.0}), base))

    def test_null_floor_is_not_a_jump(self):
        # A floor going unmeasured is not a 58 dB change.
        a = base_ctx(ambient={"noise_floor_db": None, "noise_level": "quiet"})
        self.assertFalse(materially_changed(a, base_ctx()))

    def test_greeting_crossing_cooldown_is_material(self):
        a = base_ctx(robot={"last_spoke_s_ago": 29.0})
        b = base_ctx(robot={"last_spoke_s_ago": 31.0})
        self.assertTrue(materially_changed(b, a))
        c = base_ctx(robot={"last_spoke_s_ago": 20.0})
        self.assertFalse(materially_changed(c, a))

    def test_stale_forces_reask(self):
        state = GateState()
        note_asked(state, base_ctx(t=0.0))
        ok, reason = should_ask_llm(base_ctx(t=11.0), state)  # > max_stale_sec
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")


class ContractTests(unittest.TestCase):
    def test_base_ctx_is_valid(self):
        validate(base_ctx())

    def test_rejects_v1(self):
        with self.assertRaises(ValueError):
            validate(base_ctx(schema_version="1.0"))

    def test_rejects_unknown_field(self):
        with self.assertRaises(ValueError):
            validate(base_ctx(ambient={"noise_dbfs": -50.0}))

    def test_every_vignette_is_valid(self):
        files = sorted(VIGNETTES.glob("*.json"))
        self.assertTrue(files)
        for f in files:
            with self.subTest(vignette=f.stem):
                validate(json.loads(f.read_text())["context"], f.name)

    def test_audio_node_output_while_robot_speaks(self):
        # What audio_builder._suppressed() publishes.
        audio = {
            "stamp": 1727020800.0,
            "noise_floor_db": None,
            "noise_level": None,
            "speech_snr_db": None,
            "speech_now": None,
            "speech_ratio_10s": None,
            "seconds_since_speech": None,
            "transcript": "",
            "engaged": False,
            "robot_speaking": True,
        }
        ctx = audio_to_context(audio, target=base_ctx()["target"])
        validate(ctx)
        self.assertTrue(ctx["robot"]["is_speaking"])
        self.assertIsNone(ctx["target"].get("speech"))
        ok, reason = should_ask_llm(ctx, GateState())
        self.assertFalse(ok)
        self.assertEqual(reason, "self_speaking")

    def test_audio_transcript_lands_on_target(self):
        audio = {
            "stamp": 1727020800.0,
            "noise_floor_db": -58.4,
            "noise_level": "quiet",
            "speech_snr_db": 21.3,
            "speech_now": True,
            "speech_ratio_10s": 0.2,
            "seconds_since_speech": 0.0,
            "transcript": "do you know where",
            "engaged": True,
            "robot_speaking": False,
        }
        ctx = audio_to_context(audio, target=base_ctx()["target"])
        validate(ctx)
        self.assertEqual(ctx["target"]["speech"]["partial_transcript"], "do you know where")
        self.assertTrue(ctx["robot"]["engaged"])


def approach_sequence(n=100, dt=1.0 / 3.0):
    """Person approaches, pauses facing the robot, then walks away.

    ~100 ticks at 3 Hz ≈ 33 seconds of wall-clock scene time.
    """
    ticks = []
    for i in range(n):
        t = i * dt
        if i < 30:
            # approaching from 6 m → 2 m
            dist = 6.0 - (4.0 * i / 30.0)
            target = {
                "distance_m": dist,
                "facing_robot": True,
                "motion": "approaching",
                "in_conversation": False,
            }
        elif i < 70:
            # standing still, facing
            target = {
                "distance_m": 2.0,
                "facing_robot": True,
                "motion": "stationary",
                "in_conversation": False,
            }
        else:
            # leaving
            dist = 2.0 + (4.0 * (i - 70) / 30.0)
            target = {
                "distance_m": dist,
                "facing_robot": False,
                "motion": "leaving",
                "in_conversation": False,
            }
        ticks.append(base_ctx(t=t, target=target))
    return ticks


def run_simulation(ticks, cfg=None):
    state = GateState()
    cfg = cfg or DEFAULTS
    log = []
    for ctx in ticks:
        ok, reason = decide_tick(ctx, state, cfg)
        if ok:
            note_asked(state, ctx)
        log.append((ok, reason))
    return state, log


class GateSimulationTests(unittest.TestCase):
    def test_suppression_above_90(self):
        state, log = run_simulation(approach_sequence(100))
        rate = state.suppression_rate
        self.assertGreaterEqual(
            rate,
            0.90,
            "suppression %.1f%% < 90%%; asks=%d suppressions=%s"
            % (100 * rate, state.asks, state.suppressions),
        )
        self.assertGreater(state.asks, 0, "gate must ask at least once")
        # First tick with a person should be an ask
        self.assertTrue(log[0][0])


def main():
    print("running unit + simulation tests...\n")
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    state, log = run_simulation(approach_sequence(100))
    print("\n--- approach / pause / leave @ 3 Hz, 100 ticks ---")
    print("asks:         %d" % state.asks)
    print("suppressions: %s" % dict(sorted(state.suppressions.items())))
    print("rate:         %.1f%% suppressed" % (100 * state.suppression_rate))
    reasons = {}
    for ok, reason in log:
        if not ok:
            reasons[reason] = reasons.get(reason, 0) + 1
    print("top reasons:  %s" % reasons)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
