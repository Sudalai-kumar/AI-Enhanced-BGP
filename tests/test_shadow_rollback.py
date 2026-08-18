"""
Unit tests for Shadow Validation with Fake Injected Clock and Multi-Criteria Rollback.
Zero fragile sleep() calls.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.policy.shadow_validator import ShadowValidator
from src.policy.rollback_manager import RollbackManager

class SimulatedClock:
    def __init__(self, start_time: float = 1000.0):
        self.current_time = start_time
    def time(self) -> float:
        return self.current_time
    def advance(self, seconds: float):
        self.current_time += seconds

class TestShadowAndRollbackDeterministic(unittest.TestCase):
    def setUp(self):
        self.sim_clock = SimulatedClock(1000.0)
        self.validator = ShadowValidator(
            shadow_duration_sec=5.0,
            required_consecutive_ticks=2,
            min_dwell_sec=10.0,
            clock=self.sim_clock.time
        )
        self.rollback = RollbackManager(required_normal_ticks=3)

    def test_deterministic_shadow_promotion(self):
        prefix = "192.0.2.0/24"
        # Tick 1 at t=1000.0
        promoted, _ = self.validator.submit_observation(prefix, target_loc_pref=80, target_community=None, class_id=1)
        self.assertFalse(promoted)
        self.assertIn(prefix, self.validator.shadow_queue)

        # Advance clock by 5.5s (exceeding shadow duration)
        self.sim_clock.advance(5.5)

        # Tick 2 at t=1005.5
        promoted, reason = self.validator.submit_observation(prefix, target_loc_pref=80, target_community=None, class_id=1)
        self.assertTrue(promoted)
        self.assertNotIn(prefix, self.validator.shadow_queue)

    def test_deterministic_shadow_streak_break(self):
        prefix = "198.51.100.0/24"
        self.validator.submit_observation(prefix, target_loc_pref=80, target_community=None, class_id=1)
        self.assertIn(prefix, self.validator.shadow_queue)

        # Normal observation breaks streak immediately
        promoted, _ = self.validator.submit_observation(prefix, target_loc_pref=100, target_community=None, class_id=0)
        self.assertFalse(promoted)
        self.assertNotIn(prefix, self.validator.shadow_queue)

    def test_immediate_quarantine_bypass(self):
        prefix = "192.0.2.0/24"
        # Hijack (LP 0) promotes immediately without staging delay
        promoted, _ = self.validator.submit_observation(prefix, target_loc_pref=0, target_community="no-export", class_id=3)
        self.assertTrue(promoted)

    def test_multi_criteria_rollback(self):
        prefix = "192.0.2.0/24"
        self.rollback.register_policy_modification(prefix, applied_loc_pref=80, applied_community=None)

        # Observation 1: Normal, but path unstable -> No streak advance
        rb, _ = self.rollback.process_observation(prefix, is_normal=True, path_stable=False)
        self.assertFalse(rb)
        self.assertEqual(self.rollback.recovery_streaks.get(prefix, 0), 0)

        # Observation 2, 3, 4: All criteria healthy -> Streak advances & triggers rollback on 3rd tick
        self.rollback.process_observation(prefix, is_normal=True, origin_stable=True, path_stable=True, flaps_quiescent=True) # 1
        self.rollback.process_observation(prefix, is_normal=True, origin_stable=True, path_stable=True, flaps_quiescent=True) # 2
        rb, reason = self.rollback.process_observation(prefix, is_normal=True, origin_stable=True, path_stable=True, flaps_quiescent=True) # 3

        self.assertTrue(rb)
        self.assertNotIn(prefix, self.rollback.active_modifications)

if __name__ == "__main__":
    unittest.main()
