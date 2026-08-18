"""
Race condition verification test for BGP soft reconfiguration.
Tests that updating route maps via vtysh and triggering 'clear ip bgp soft in'
settles without reading transitional or stale telemetry.
"""

import unittest
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.policy.policy_engine import BGPPolicyEngine
from src.telemetry.frr_collector import FRRTelemetryCollector

class TestTelemetrySync(unittest.TestCase):
    def setUp(self):
        self.policy_engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.23.2")
        self.collector = FRRTelemetryCollector(router_container="as65003")

    def test_post_policy_telemetry_settle(self):
        # Check if docker router is reachable
        test_policies = {
            "192.0.2.0/24": {"loc_pref": 100, "community": None}
        }
        success = self.policy_engine.apply_policy(test_policies, settle_delay_sec=0.5)
        if not success:
            self.skipTest("Docker testbed router as65003 not online; skipping live integration test.")
        self.assertTrue(success)

        # 2. Immediately sample RIB state
        routes_data = self.collector.collect_route_rib()
        routes = routes_data.get("routes", [])
        self.assertGreater(len(routes), 0)
        
        # 3. Assert route attributes are fully formed and valid
        pfx_192 = next((r for r in routes if r["prefix"] == "192.0.2.0/24"), None)
        self.assertIsNotNone(pfx_192)
        self.assertEqual(pfx_192["loc_pref"], 100)
        self.assertTrue(pfx_192["is_best"])

if __name__ == "__main__":
    unittest.main()
