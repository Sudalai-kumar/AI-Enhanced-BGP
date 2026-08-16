"""
Unit tests for Shadow Validation, Streak Breaking, Hysteresis, and Automatic Rollback.
"""

import unittest
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.policy.shadow_validator import ShadowValidator
from src.policy.rollback_manager import RollbackManager

class TestShadowAndRollback(unittest.TestCase):
    def setUp(self):
        self.validator = ShadowValidator(shadow_duration_sec=0.2, required_consecutive_ticks=2, min_dwell_sec=0.5)
        self.rollback = RollbackManager(required_normal_ticks=3)

    def test_shadow_validation_streak_and_promotion(self):
        prefix = "192.0.2.0/24"
        
        # Tick 1: Placed in shadow queue
        promoted, reason = self.validator.submit_observation(prefix, target_loc_pref=80, target_community=None, class_id=1)
        self.assertFalse(promoted)
        self.assertIn(prefix, self.validator.shadow_queue)
        
        time.sleep(0.25)
        # Tick 2: Validated & Promoted
        promoted, reason = self.validator.submit_observation(prefix, target_loc_pref=80, target_community=None, class_id=1)
        self.assertTrue(promoted)
        self.assertNotIn(prefix, self.validator.shadow_queue)

    def test_shadow_validation_streak_break(self):
        prefix = "198.51.100.0/24"
        
        # Tick 1: Suspicious observation (in queue)
        self.validator.submit_observation(prefix, target_loc_pref=80, target_community=None, class_id=1)
        self.assertIn(prefix, self.validator.shadow_queue)
        
        # Tick 2: Normal observation -> streak broken & queue cleared
        promoted, reason = self.validator.submit_observation(prefix, target_loc_pref=100, target_community=None, class_id=0)
        self.assertFalse(promoted)
        self.assertNotIn(prefix, self.validator.shadow_queue)

    def test_immediate_quarantine_promotion(self):
        prefix = "192.0.2.0/24"
        # Hijack (LP 0) promotes immediately without waiting full duration
        promoted, reason = self.validator.submit_observation(prefix, target_loc_pref=0, target_community="no-export", class_id=3)
        self.assertTrue(promoted)

    def test_rollback_lifecycle_and_conflict_reset(self):
        prefix = "192.0.2.0/24"
        self.rollback.register_policy_modification(prefix, applied_loc_pref=80, applied_community=None)
        
        # Observation 1: Normal
        rb, _ = self.rollback.process_observation(prefix, is_normal=True)
        self.assertFalse(rb)
        
        # Observation 2: Anomaly regressed! Streak resets
        rb, _ = self.rollback.process_observation(prefix, is_normal=False)
        self.assertFalse(rb)
        self.assertEqual(self.rollback.recovery_streaks[prefix], 0)
        
        # 3 Consecutive Normal observations
        self.rollback.process_observation(prefix, is_normal=True) # 1
        self.rollback.process_observation(prefix, is_normal=True) # 2
        rb, reason = self.rollback.process_observation(prefix, is_normal=True) # 3
        
        self.assertTrue(rb)
        self.assertNotIn(prefix, self.rollback.active_modifications)

if __name__ == "__main__":
    unittest.main()
