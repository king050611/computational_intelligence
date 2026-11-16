import unittest
from src.search.time_manager import TimeManager, time_exceeded


class ClockTests(unittest.TestCase):
    def test_cumulative_budget_and_safety_margin(self):
        clock = TimeManager(60, 5)
        self.assertAlmostEqual(clock.allocate_time(10), 5.5)
        clock.record_elapsed(50)
        self.assertAlmostEqual(clock.allocate_time(10), 0.5)
        clock.record_elapsed(6)
        self.assertEqual(clock.allocate_time(), 0)
        self.assertTrue(time_exceeded(0))

    @unittest.skip("TODO B: implement search before validating tactical decisions")
    def test_search_tactics_and_pruning_equivalence(self):
        pass
