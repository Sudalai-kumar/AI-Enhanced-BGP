"""
Unit tests for BGP Feature Extraction Engine.
"""

import unittest
import numpy as np
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.ai.feature_extractor import BGPFeatureExtractor, levenshtein_distance, check_valley_free_violation

class TestBGPFeatureExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = BGPFeatureExtractor(
            historical_baseline_as_paths={"192.0.2.0/24": ["65002", "65001"]},
            historical_origins={"192.0.2.0/24": 65001},
            total_configured_neighbors=2
        )

    def test_levenshtein_distance(self):
        d1 = levenshtein_distance(["65002", "65001"], ["65002", "65001"])
        self.assertEqual(d1, 0)
        d2 = levenshtein_distance(["65002", "65001"], ["65004", "65001"])
        self.assertEqual(d2, 1)
        d3 = levenshtein_distance(["65002", "65001"], ["65003", "65002", "65001"])
        self.assertEqual(d3, 1)

    def test_valley_free_violation(self):
        self.assertEqual(check_valley_free_violation(["65002", "65001"]), 0)
        self.assertEqual(check_valley_free_violation(["65002", "65001", "65002"]), 1) # Loop

    def test_feature_vector_dimensions_and_types(self):
        route = {
            "prefix": "192.0.2.0/24",
            "as_path": "65002 65001",
            "origin_as": 65001,
            "loc_pref": 100
        }
        history = [
            {"timestamp": time.time() - 30, "as_path": "65002 65001", "origin_as": 65001},
            {"timestamp": time.time(), "as_path": "65002 65001", "origin_as": 65001}
        ]
        
        feat = self.extractor.extract_features("192.0.2.0/24", route, history, active_neighbors_announcing=1)
        self.assertEqual(feat.shape, (10,))
        self.assertEqual(feat[0], 2.0) # as_path_len = 2
        self.assertEqual(feat[1], 0.0) # edit_dist = 0
        self.assertEqual(feat[2], 0.0) # origin_change = 0
        self.assertEqual(feat[3], 24.0) # /24 mask
        self.assertEqual(feat[9], 0.5) # 1/2 neighbors

if __name__ == "__main__":
    unittest.main()
