"""
Unit tests for BGP Policy Engine and Quarantine mechanisms.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.policy.policy_engine import BGPPolicyEngine

class TestPolicyEngine(unittest.TestCase):
    def setUp(self):
        self.engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.23.2", route_map_name="RM_IN_AS65002")

    def test_trust_to_policy_mapping(self):
        # 1. Normal State
        lp, comm, desc = self.engine.map_trust_to_policy(trust_score=0.95, class_id=0, current_loc_pref=100)
        self.assertEqual(lp, 100)
        self.assertIsNone(comm)
        
        # 2. Suspicious Flap State
        lp, comm, desc = self.engine.map_trust_to_policy(trust_score=0.65, class_id=1, current_loc_pref=100)
        self.assertEqual(lp, 80)
        self.assertIsNone(comm)
        
        # 3. Route Leak State
        lp, comm, desc = self.engine.map_trust_to_policy(trust_score=0.35, class_id=2, current_loc_pref=100)
        self.assertEqual(lp, 50)
        self.assertIsNone(comm)
        
        # 4. Dual Quarantine (Hijack State)
        lp, comm, desc = self.engine.map_trust_to_policy(trust_score=0.10, class_id=3, current_loc_pref=100)
        self.assertEqual(lp, 0)
        self.assertEqual(comm, "no-export")

    def test_route_map_syntax_generation(self):
        policies = {
            "192.0.2.0/24": {"loc_pref": 80, "community": None},
            "198.51.100.0/24": {"loc_pref": 0, "community": "no-export"}
        }
        config_text = self.engine.generate_route_map_config(policies)
        
        self.assertIn("route-map RM_IN_AS65002 permit 10", config_text)
        self.assertIn("set local-preference 80", config_text)
        self.assertIn("route-map RM_IN_AS65002 permit 20", config_text)
        self.assertIn("set local-preference 0", config_text)
        self.assertIn("set community no-export", config_text)
        self.assertIn("route-map RM_IN_AS65002 permit 1000", config_text)

if __name__ == "__main__":
    unittest.main()
