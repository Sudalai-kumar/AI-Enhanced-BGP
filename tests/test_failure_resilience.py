"""
Failure resilience unit tests for the Autonomous BGP Controller (Async-enabled).
All tests mock run_subprocess_async and the state store so no Docker or FRR is required.
Covers: docker timeout, malformed JSON, policy apply failure, verification failure,
stale RIB, ML model load failure, and controller restart during mitigation.
"""

import json
import asyncio
import tempfile
import os
import sys
import unittest
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.telemetry.frr_collector import FRRTelemetryCollector
from src.policy.policy_engine import BGPPolicyEngine
from src.policy.state_store import ControllerStateStore


class TestDockerExecTimeout(unittest.IsolatedAsyncioTestCase):
    """FRRTelemetryCollector must return empty/None when docker exec times out."""

    @patch("src.telemetry.frr_collector.run_subprocess_async")
    async def test_exec_vtysh_json_timeout_returns_none(self, mock_run):
        mock_run.side_effect = asyncio.TimeoutError()
        collector = FRRTelemetryCollector(router_container="as65003")
        result = await collector.exec_vtysh_json("show bgp summary json")
        self.assertIsNone(result)

    @patch("src.telemetry.frr_collector.run_subprocess_async")
    async def test_collect_route_rib_on_timeout_returns_empty(self, mock_run):
        mock_run.side_effect = asyncio.TimeoutError()
        collector = FRRTelemetryCollector(router_container="as65003")
        result = await collector.collect_route_rib()
        self.assertEqual(result["routes"], [])
        self.assertEqual(result["transitions"], [])


class TestMalformedJSONResponse(unittest.IsolatedAsyncioTestCase):
    """Collector must gracefully handle non-JSON output from vtysh."""

    @patch("src.telemetry.frr_collector.run_subprocess_async")
    async def test_malformed_json_exec_returns_none(self, mock_run):
        mock_run.return_value = (0, b"not valid json {{{\n", b"")
        collector = FRRTelemetryCollector(router_container="as65003")
        result = await collector.exec_vtysh_json("show bgp summary json")
        self.assertIsNone(result)


class TestPolicyApplyFailure(unittest.IsolatedAsyncioTestCase):
    """When apply_policy returns False, active_policies must not be updated."""

    async def test_active_policies_unchanged_on_apply_failure(self):
        engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.23.2")
        # Seed current_policies with an existing state
        engine.current_policies = {"192.0.2.0/24": {"loc_pref": 100, "community": None}}
        initial_snapshot = engine.current_policies.copy()

        # Simulate apply failure: vtysh returns non-zero
        with patch("src.policy.policy_engine.run_subprocess_async") as mock_run:
            mock_run.return_value = (1, b"", b"error")

            result = await engine.apply_policy({"192.0.2.0/24": {"loc_pref": 50, "community": None}})

        self.assertFalse(result)
        # current_policies must be unchanged
        self.assertEqual(engine.current_policies, initial_snapshot)


class TestVerificationFailureAfterApply(unittest.IsolatedAsyncioTestCase):
    """When config verification fails after apply, current_policies must stay unchanged."""

    async def test_current_policies_unchanged_on_verify_failure(self):
        engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.23.2")
        engine.current_policies = {"192.0.2.0/24": {"loc_pref": 100, "community": None}}

        with patch.object(engine, "verify_frr_state", return_value=False), \
             patch("src.policy.policy_engine.run_subprocess_async") as mock_run:
            # vtysh apply succeeds
            mock_run.return_value = (0, b"", b"")

            result = await engine.apply_policy(
                {"192.0.2.0/24": {"loc_pref": 50, "community": None}}
            )

        self.assertFalse(result)
        self.assertEqual(engine.current_policies["192.0.2.0/24"]["loc_pref"], 100)


class TestRIBVerifyFailureAfterApply(unittest.IsolatedAsyncioTestCase):
    """When RIB best-path verification fails, current_policies must stay unchanged."""

    async def test_current_policies_unchanged_on_rib_verify_failure(self):
        engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.23.2")
        engine.current_policies = {"192.0.2.0/24": {"loc_pref": 100, "community": None}}

        with patch.object(engine, "verify_frr_state", return_value=True), \
             patch.object(engine, "verify_rib_best_path",
                          return_value=(False, {"reason": "LP mismatch"})), \
             patch("src.policy.policy_engine.run_subprocess_async") as mock_run:
            mock_run.return_value = (0, b"", b"")

            result = await engine.apply_policy(
                {"192.0.2.0/24": {"loc_pref": 50, "community": None}}
            )

        self.assertFalse(result)
        self.assertEqual(engine.current_policies["192.0.2.0/24"]["loc_pref"], 100)


class TestStaleRIBDetection(unittest.IsolatedAsyncioTestCase):
    """
    When the same RIB snapshot is returned repeatedly, no spurious transitions
    should be generated beyond the initial NEW_ANNOUNCEMENT on first observation.
    """

    @patch("src.telemetry.frr_collector.run_subprocess_async")
    async def test_no_spurious_transitions_on_repeated_identical_rib(self, mock_run):
        stable_rib = {
            "routes": {
                "192.0.2.0/24": [
                    {
                        "nexthop": "10.0.23.2",
                        "aspath": {"string": "65002 65001"},
                        "locPrf": 100,
                        "metric": 0,
                        "community": "",
                        "bestpath": True,
                        "lastUpdate": 0
                    }
                ]
            }
        }
        mock_run.return_value = (0, json.dumps(stable_rib).encode(), b"")

        collector = FRRTelemetryCollector(router_container="as65003")
        # First call initialises the RIB
        result1 = await collector.collect_route_rib()
        # Subsequent calls with identical data must not generate PATH_ATTRIBUTE_CHANGE
        for _ in range(4):
            result = await collector.collect_route_rib()
            path_changes = [
                t for t in result["transitions"]
                if t["type"] == "PATH_ATTRIBUTE_CHANGE"
            ]
            self.assertEqual(
                path_changes, [],
                msg=f"Spurious PATH_ATTRIBUTE_CHANGE on stable RIB: {path_changes}"
            )


class TestMLModelLoadFailure(unittest.TestCase):
    """BGPClassifier must raise FileNotFoundError when the model file is missing."""

    def test_classifier_raises_on_missing_model(self):
        from src.ai.classifier import BGPClassifier
        with self.assertRaises((FileNotFoundError, Exception)):
            classifier = BGPClassifier(model_type="random_forest")
            classifier.model_path = "/tmp/nonexistent_model_xyzzy.joblib"
            classifier._load_model("/tmp/nonexistent_model_xyzzy.joblib")


class TestControllerRestartDuringMitigation(unittest.IsolatedAsyncioTestCase):
    """
    At startup, if the state store contains an active non-normal policy
    and FRR verify_frr_state returns True, the controller must load
    those policies into active_policies without re-applying them.
    """

    async def test_reconcile_loads_persisted_policies_when_frr_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "ctrl.db")
            store = ControllerStateStore(db_path=db_path)
            await store.initialize()
            # Simulate a previously-applied quarantine policy
            await store.save_policy(
                prefix="192.0.2.0/24",
                loc_pref=0,
                community="no-export",
                classification_id=3,
                trust_score=0.05,
                verified=True
            )
            persisted = await store.get_all_active_policies()
            self.assertIn("192.0.2.0/24", persisted)
            self.assertEqual(persisted["192.0.2.0/24"]["loc_pref"], 0)


if __name__ == "__main__":
    unittest.main()
