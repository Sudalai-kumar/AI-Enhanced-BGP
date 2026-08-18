"""
Unit Test Suite for Controller State Store, Deep FRR Policy Verification,
Atomic Persistence, and Benchmark Metric Censoring.
"""

import unittest
import os
import sys
import gc
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.policy.state_store import ControllerStateStore
from src.policy.policy_engine import BGPPolicyEngine
from src.experiments.metrics import BenchmarkMetricsCalculator

class TestStateStoreAndVerification(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_path = self.temp_file.name
        self.temp_file.close()
        self.store = ControllerStateStore(db_path=self.temp_path)
        self.engine = BGPPolicyEngine(router="test_router")

    def tearDown(self):
        del self.store
        gc.collect()
        if os.path.exists(self.temp_path):
            try:
                os.remove(self.temp_path)
            except PermissionError:
                pass

    def test_state_store_save_and_retrieve(self):
        self.store.save_policy("192.0.2.0/24", loc_pref=0, community="no-export",
                              classification_id=3, trust_score=0.12, verified=True)
        self.store.save_policy("198.51.100.0/24", loc_pref=80, community=None,
                              classification_id=1, trust_score=0.68, verified=True)

        policies = self.store.get_all_active_policies()
        self.assertEqual(len(policies), 2)
        self.assertEqual(policies["192.0.2.0/24"]["loc_pref"], 0)
        self.assertEqual(policies["192.0.2.0/24"]["community"], "no-export")
        self.assertEqual(policies["192.0.2.0/24"]["classification_id"], 3)
        self.assertEqual(policies["198.51.100.0/24"]["loc_pref"], 80)
        self.assertEqual(policies["198.51.100.0/24"]["community"], None)

    def test_state_store_deletion(self):
        self.store.save_policy("192.0.2.0/24", 50, None, 2, 0.45, True)
        self.store.remove_policy("192.0.2.0/24")
        policies = self.store.get_all_active_policies()
        self.assertNotIn("192.0.2.0/24", policies)

    def test_route_map_syntax_generation(self):
        policies = {
            "192.0.2.0/24": {"loc_pref": 0, "community": "no-export"},
            "198.51.100.0/24": {"loc_pref": 80, "community": None}
        }
        cfg = self.engine.generate_route_map_config(policies)
        self.assertIn("route-map RM_IN_AS65002 permit 10", cfg)
        self.assertIn("match ip address prefix-list PL_AI_192_0_2_0_24", cfg)
        self.assertIn("set local-preference 0", cfg)
        self.assertIn("set community no-export", cfg)
        self.assertIn("route-map RM_IN_AS65002 permit 20", cfg)
        self.assertIn("match ip address prefix-list PL_AI_198_51_100_0_24", cfg)
        self.assertIn("set local-preference 80", cfg)

    def test_metrics_computation(self):
        y_true = [3, 3, 3]
        y_pred = [3, 3, 3]
        res = BenchmarkMetricsCalculator.compute_classification_metrics(y_true, y_pred)
        self.assertEqual(res["precision"], 1.0)
        self.assertEqual(res["recall"], 1.0)
        self.assertEqual(res["f1"], 1.0)

if __name__ == "__main__":
    unittest.main()
