"""
Unit tests for Gao-Rexford Valley-Free and 10-Feature Behavioral Extractor.
Tests:
- Valid customer-provider-customer paths
- Valid peer-to-peer single hop
- Invalid valley-free violations (peer-provider-peer, customer-peer-customer detour)
- True route age preservation
- Rolling 5-minute flap calculation
"""

import unittest
import numpy as np
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.ai.feature_extractor import BGPFeatureExtractor

class TestFeatureExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = BGPFeatureExtractor(baseline_origin_as=65001, baseline_as_path="65002 65001")

    def test_valley_free_valid_paths(self):
        # 1. Valid Direct transit: AS65002 (Transit) -> AS65001 (Customer)
        self.assertEqual(self.extractor.check_valley_free_violation("65002 65001"), 0)
        
        # 2. Valid Single Peer Hop: AS65003 (Peer) -> AS65002 (Peer) -> AS65001 (Customer)
        self.assertEqual(self.extractor.check_valley_free_violation("65003 65002 65001"), 0)

    def test_valley_free_violations(self):
        # 1. AS Loop: 65002 65001 65002 -> Violation (1)
        self.assertEqual(self.extractor.check_valley_free_violation("65002 65001 65002"), 1)

        # 2. Downward followed by Upward: Provider -> Customer -> Provider (AS65002 -> AS15169 -> AS12389)
        self.assertEqual(self.extractor.check_valley_free_violation("65002 12389 12389 15169"), 1)

        # 3. Customer-to-Peer Leak: Allegheny (AS396531) leaking Cloudflare (AS13335) via Verizon (AS701)
        self.assertEqual(self.extractor.check_valley_free_violation("65002 701 396531 13335"), 1)

    def test_true_route_age_preservation(self):
        now = time.time()
        # Route created 3.5 seconds ago (young route)
        current_route = {
            "origin_as": 65001,
            "as_path": "65002 65001",
            "last_update_epoch": now - 3.5,
            "loc_pref": 100
        }
        features = self.extractor.extract_features("192.0.2.0/24", current_route, [])
        # Assert route age is NOT artificially rewritten to 600s
        self.assertAlmostEqual(features[7], 3.5, delta=0.5)

    def test_rolling_5min_flaps(self):
        now = time.time()
        # 3 flaps within last 60s, 2 flaps from 10 minutes ago (should be excluded)
        events = [
            {"as_path": "65002 65001", "origin_as": 65001, "timestamp": now - 600}, # Old
            {"as_path": "65002 65004", "origin_as": 65004, "timestamp": now - 500}, # Old
            {"as_path": "65002 65001", "origin_as": 65001, "timestamp": now - 40},  # Recent
            {"as_path": "65002 65004", "origin_as": 65004, "timestamp": now - 30},  # Recent
            {"as_path": "65002 65001", "origin_as": 65001, "timestamp": now - 10}   # Recent
        ]
        current_route = {"origin_as": 65001, "as_path": "65002 65001", "loc_pref": 100}
        features = self.extractor.extract_features("192.0.2.0/24", current_route, events)
        # Only transitions within 300s window counted
        self.assertEqual(features[5], 2.0)

if __name__ == "__main__":
    unittest.main()
