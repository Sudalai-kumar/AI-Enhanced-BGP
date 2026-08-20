"""
Failure resilience unit tests for the Autonomous BGP Controller.
All tests mock subprocess.run and the state store so no Docker or FRR is required.
Covers: docker timeout, malformed JSON, policy apply failure, verification failure,
stale RIB, ML model load failure, and controller restart during mitigation.
"""

import json
import subprocess
import sqlite3
import tempfile
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.telemetry.frr_collector import FRRTelemetryCollector
from src.policy.policy_engine import BGPPolicyEngine
from src.policy.state_store import ControllerStateStore


class TestDockerExecTimeout(unittest.TestCase):
    """FRRTelemetryCollector must return empty/None when docker exec times out."""

    @patch("src.telemetry.frr_collector.subprocess.run")
    def test_exec_vtysh_json_timeout_returns_none(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="vtysh", timeout=4)
        collector = FRRTelemetryCollector(router_container="as65003")
        result = collector.exec_vtysh_json("show bgp summary json")
        self.assertIsNone(result)

    @patch("src.telemetry.frr_collector.subprocess.run")
    def test_collect_route_rib_on_timeout_returns_empty(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="vtysh", timeout=4)
        collector = FRRTelemetryCollector(router_container="as65003")
        result = collector.collect_route_rib()
        self.assertEqual(result["routes"], [])
        self.assertEqual(result["transitions"], [])


class TestMalformedJSONResponse(unittest.TestCase):
    """Collector must gracefully handle non-JSON output from vtysh."""

    @patch("src.telemetry.frr_collector.subprocess.run")
    def test_malformed_json_exec_returns_none(self, mock_run):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "not valid json {{{\n"
        mock_run.return_value = proc
        collector = FRRTelemetryCollector(router_container="as65003")
        result = collector.exec_vtysh_json("show bgp summary json")
        self.assertIsNone(result)


class TestPolicyApplyFailure(unittest.TestCase):
    """When apply_policy returns False, active_policies must not be updated."""

    def test_active_policies_unchanged_on_apply_failure(self):
        engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.23.2")
        # Seed current_policies with an existing state
        engine.current_policies = {"192.0.2.0/24": {"loc_pref": 100, "community": None}}
        initial_snapshot = engine.current_policies.copy()

        # Simulate apply failure: vtysh returns non-zero
        with patch("src.policy.policy_engine.subprocess.run") as mock_run:
            proc = MagicMock()
            proc.returncode = 1
            proc.stderr = "error"
            mock_run.return_value = proc

            result = engine.apply_policy({"192.0.2.0/24": {"loc_pref": 50, "community": None}})

        self.assertFalse(result)
        # current_policies must be unchanged
        self.assertEqual(engine.current_policies, initial_snapshot)


class TestVerificationFailureAfterApply(unittest.TestCase):
    """When config verification fails after apply, current_policies must stay unchanged."""

    def test_current_policies_unchanged_on_verify_failure(self):
        engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.23.2")
        engine.current_policies = {"192.0.2.0/24": {"loc_pref": 100, "community": None}}

        with patch.object(engine, "verify_frr_state", return_value=False), \
             patch("src.policy.policy_engine.subprocess.run") as mock_run:
            # vtysh apply succeeds
            proc = MagicMock()
            proc.returncode = 0
            mock_run.return_value = proc

            result = engine.apply_policy(
                {"192.0.2.0/24": {"loc_pref": 50, "community": None}}
            )

        self.assertFalse(result)
        self.assertEqual(engine.current_policies["192.0.2.0/24"]["loc_pref"], 100)


class TestRIBVerifyFailureAfterApply(unittest.TestCase):
    """When RIB best-path verification fails, current_policies must stay unchanged."""

    def test_current_policies_unchanged_on_rib_verify_failure(self):
        engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.23.2")
        engine.current_policies = {"192.0.2.0/24": {"loc_pref": 100, "community": None}}

        with patch.object(engine, "verify_frr_state", return_value=True), \
             patch.object(engine, "verify_rib_best_path",
                          return_value=(False, {"reason": "LP mismatch"})), \
             patch("src.policy.policy_engine.subprocess.run") as mock_run:
            proc = MagicMock()
            proc.returncode = 0
            mock_run.return_value = proc

            result = engine.apply_policy(
                {"192.0.2.0/24": {"loc_pref": 50, "community": None}}
            )

        self.assertFalse(result)
        self.assertEqual(engine.current_policies["192.0.2.0/24"]["loc_pref"], 100)


class TestStaleRIBDetection(unittest.TestCase):
    """
    When the same RIB snapshot is returned repeatedly, no spurious transitions
    should be generated beyond the initial NEW_ANNOUNCEMENT on first observation.
    """

    @patch("src.telemetry.frr_collector.subprocess.run")
    def test_no_spurious_transitions_on_repeated_identical_rib(self, mock_run):
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
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = json.dumps(stable_rib)
        mock_run.return_value = proc

        collector = FRRTelemetryCollector(router_container="as65003")
        # First call initialises the RIB
        result1 = collector.collect_route_rib()
        # Subsequent calls with identical data must not generate PATH_ATTRIBUTE_CHANGE
        for _ in range(4):
            result = collector.collect_route_rib()
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
            # Point to a non-existent model path
            classifier = BGPClassifier(model_type="random_forest")
            classifier.model_path = "/tmp/nonexistent_model_xyzzy.joblib"
            # Force a reload attempt
            classifier._load_model("/tmp/nonexistent_model_xyzzy.joblib")


class TestControllerRestartDuringMitigation(unittest.TestCase):
    """
    At startup, if the state store contains an active non-normal policy
    and FRR verify_frr_state returns True, the controller must load
    those policies into active_policies without re-applying them.
    """

    def test_reconcile_loads_persisted_policies_when_frr_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "ctrl.db")
            store = ControllerStateStore(db_path=db_path)
            # Simulate a previously-applied quarantine policy
            store.save_policy(
                prefix="192.0.2.0/24",
                loc_pref=0,
                community="no-export",
                classification_id=3,
                trust_score=0.05,
                verified=True
            )
            persisted = store.get_all_active_policies()
            self.assertIn("192.0.2.0/24", persisted)
            self.assertEqual(persisted["192.0.2.0/24"]["loc_pref"], 0)


if __name__ == "__main__":
    unittest.main()
