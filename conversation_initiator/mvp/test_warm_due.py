import unittest

from mvp import WARM_EVERY_S, KEEPALIVE_S, warm_due


class WarmDueTests(unittest.TestCase):
    def test_due_only_with_a_person_and_idle_long_enough(self):
        self.assertTrue(warm_due(100.0, 100.0 - WARM_EVERY_S, True))
        self.assertFalse(warm_due(100.0, 100.0 - WARM_EVERY_S + 1, True))
        self.assertFalse(warm_due(1000.0, 0.0, False))

    def test_it_runs_before_the_connection_closes(self):
        self.assertLess(WARM_EVERY_S, KEEPALIVE_S)


if __name__ == "__main__":
    unittest.main()
