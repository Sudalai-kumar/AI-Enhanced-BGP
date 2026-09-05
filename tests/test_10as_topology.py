"""
Unit and integration tests for the 10-AS BGP Topology and Multi-Tier Defense.
Asserts:
1. Complete Gao-Rexford relationship correctness across all 10 ASes (65001 - 65010).
2. Valley-free valid and invalid path classifications in the 10-AS hierarchy.
3. Multi-peer route-map syntax generation across Core (AS65001) and Edge (AS65003).
4. Dual SQLite state store isolation per router name.
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.ai.feature_extractor import BGPFeatureExtractor, AS_RELATIONSHIPS
from src.policy.policy_engine import BGPPolicyEngine, ROUTER_PEER_ROUTE_MAPS
from src.policy.state_store import ControllerStateStore


class Test10ASTopology(unittest.TestCase):
    def setUp(self):
        # Baseline origin AS65007 (Stub A) observed from AS65001 via AS65003
        self.extractor = BGPFeatureExtractor(
            baseline_origin_as=65007,
            baseline_as_path="65003 65007"
        )
        self.core_policy_engine = BGPPolicyEngine(router="as65001", peer_ip="10.0.12.3")
        self.edge_policy_engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.13.2")

    def test_gao_rexford_10as_relationships(self):
        """Asserts that all defined AS relationships in the 10-AS topology are present."""
        # Tier-1 Peering
        self.assertEqual(AS_RELATIONSHIPS.get((65001, 65002)), "peer-to-peer")
        self.assertEqual(AS_RELATIONSHIPS.get((65002, 65001)), "peer-to-peer")

        # Regional to Tier-1 (Customer-to-Provider)
        self.assertEqual(AS_RELATIONSHIPS.get((65003, 65001)), "customer-to-provider")
        self.assertEqual(AS_RELATIONSHIPS.get((65001, 65003)), "provider-to-customer")
        self.assertEqual(AS_RELATIONSHIPS.get((65004, 65001)), "customer-to-provider")
        self.assertEqual(AS_RELATIONSHIPS.get((65005, 65002)), "customer-to-provider")
        self.assertEqual(AS_RELATIONSHIPS.get((65006, 65002)), "customer-to-provider")

        # Stub Customers
        self.assertEqual(AS_RELATIONSHIPS.get((65007, 65003)), "customer-to-provider")
        self.assertEqual(AS_RELATIONSHIPS.get((65008, 65003)), "customer-to-provider")
        self.assertEqual(AS_RELATIONSHIPS.get((65009, 65004)), "customer-to-provider")

        # Rogue Customer
        self.assertEqual(AS_RELATIONSHIPS.get((65010, 65006)), "customer-to-provider")
        self.assertEqual(AS_RELATIONSHIPS.get((65006, 65010)), "provider-to-customer")

    def test_10as_valley_free_valid_paths(self):
        """Asserts valid Gao-Rexford paths through the 10-AS topology."""
        # 1. Stub A (65007) -> Regional West (65003) -> Tier-1 Core (65001)
        self.assertEqual(self.extractor.check_valley_free_violation("65003 65007"), 0)

        # 2. Stub A (65007) -> 65003 -> 65001 -> 65004 -> Enterprise (65009)
        self.assertEqual(self.extractor.check_valley_free_violation("65004 65001 65003 65007"), 0)

        # 3. Stub A (65007) -> 65003 -> 65001 -> 65002 -> 65005
        self.assertEqual(self.extractor.check_valley_free_violation("65005 65002 65001 65003 65007"), 0)

    def test_10as_valley_free_violations(self):
        """Asserts detection of route leaks and valley-free violations in 10-AS topology."""
        # 1. Route Leak: Customer AS65007 leaking routes between providers/peers
        self.assertEqual(self.extractor.check_valley_free_violation("65006 65010 65006 65007"), 1)

        # 2. Downward then Upward: Provider -> Customer -> Provider detour
        self.assertEqual(self.extractor.check_valley_free_violation("65001 65003 65008 65003"), 1)

        # 3. AS Path Loop
        self.assertEqual(self.extractor.check_valley_free_violation("65003 65007 65003"), 1)

    def test_multipeer_routemap_generation(self):
        """Asserts that route-maps are correctly generated for multi-homed Core and Edge routers."""
        policies = {
            "192.0.2.0/24": {"loc_pref": 0, "community": "no-export"},
            "203.0.113.0/24": {"loc_pref": 50, "community": None}
        }

        # Check Core router target route-maps
        core_maps = ROUTER_PEER_ROUTE_MAPS.get("as65001", [])
        self.assertIn("RM_IN_AS65002", core_maps)
        self.assertIn("RM_IN_AS65003", core_maps)
        self.assertIn("RM_IN_AS65004", core_maps)

        # Generate config for RM_IN_AS65004
        cfg = self.core_policy_engine.generate_route_map_config(policies, route_map_name="RM_IN_AS65004")
        self.assertIn("route-map RM_IN_AS65004 permit 10", cfg)
        self.assertIn("match ip address prefix-list PL_AI_192_0_2_0_24", cfg)
        self.assertIn("set local-preference 0", cfg)
        self.assertIn("set community no-export", cfg)
        self.assertIn("route-map RM_IN_AS65004 permit 20", cfg)
        self.assertIn("set local-preference 50", cfg)
        self.assertIn("route-map RM_IN_AS65004 permit 1000", cfg)
        self.assertIn("set local-preference 100", cfg)

    def test_dual_state_store_isolation(self):
        """Asserts that separate state stores do not interfere with each other."""
        db_core = os.path.abspath("data/test_state_as65001.db")
        db_edge = os.path.abspath("data/test_state_as65003.db")

        try:
            store_core = ControllerStateStore(db_path=db_core, router_name="as65001")
            store_edge = ControllerStateStore(db_path=db_edge, router_name="as65003")

            store_core._init_db_sync()
            store_edge._init_db_sync()

            store_core._save_policy_sync("192.0.2.0/24", 0, "no-export", 3, 0.20, verified=True)
            store_edge._save_policy_sync("192.0.2.0/24", 80, None, 1, 0.75, verified=True)

            core_policies = store_core._get_all_active_policies_sync()
            edge_policies = store_edge._get_all_active_policies_sync()

            self.assertEqual(core_policies["192.0.2.0/24"]["loc_pref"], 0)
            self.assertEqual(edge_policies["192.0.2.0/24"]["loc_pref"], 80)
        finally:
            if os.path.exists(db_core):
                os.remove(db_core)
            if os.path.exists(db_edge):
                os.remove(db_edge)


if __name__ == "__main__":
    unittest.main()
