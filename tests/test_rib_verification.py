"""
Unit tests for BGPPolicyEngine.verify_rib_best_path().
All tests use unittest.mock to patch subprocess.run so no Docker is required.
"""

import json
import subprocess
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.policy.policy_engine import BGPPolicyEngine


def _make_proc(stdout: str, returncode: int = 0) -> MagicMock:
    """Helper: returns a mock CompletedProcess."""
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = ""
    return m


DEFAULT_RIB_JSON = json.dumps({
    "paths": [
        {
            "bestpath": {"overall": True},
            "locPrf": 80,
            "community": {"string": ""}
        }
    ]
})

RIB_WITH_COMMUNITY = json.dumps({
    "paths": [
        {
            "bestpath": {"overall": True},
            "locPrf": 0,
            "community": {"string": "no-export"}
        }
    ]
})

RIB_WRONG_LP = json.dumps({
    "paths": [
        {
            "bestpath": {"overall": True},
            "locPrf": 100,     # controller set 80 but FRR still shows 100
            "community": {"string": ""}
        }
    ]
})

RIB_NO_PATHS = json.dumps({
    "paths": []
})

RIB_MISSING_COMMUNITY = json.dumps({
    "paths": [
        {
            "bestpath": {"overall": True},
            "locPrf": 0,
            "community": {"string": ""}   # community not set in RIB
        }
    ]
})


class TestVerifyRIBBestPath(unittest.TestCase):

    def setUp(self):
        self.engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.23.2")

    @patch("src.policy.policy_engine.subprocess.run")
    def test_correct_best_path_returns_true(self, mock_run):
        """Correct LP in RIB should return True."""
        mock_run.return_value = _make_proc(DEFAULT_RIB_JSON)
        ok, details = self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertTrue(ok, msg=f"Expected True but got False: {details}")
        self.assertEqual(details["reason"], "OK")

    @patch("src.policy.policy_engine.subprocess.run")
    def test_wrong_lp_in_rib_returns_false(self, mock_run):
        """If FRR RIB shows different LP than expected, should return False."""
        mock_run.return_value = _make_proc(RIB_WRONG_LP)
        ok, details = self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertFalse(ok)
        self.assertIn("mismatch", details["reason"].lower())
        self.assertEqual(details["actual_lp"], 100)

    @patch("src.policy.policy_engine.subprocess.run")
    def test_prefix_not_in_rib_returns_false(self, mock_run):
        """Empty paths list should return False."""
        mock_run.return_value = _make_proc(RIB_NO_PATHS)
        ok, details = self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertFalse(ok)
        self.assertIn("No paths", details["reason"])

    @patch("src.policy.policy_engine.subprocess.run")
    def test_timeout_returns_false(self, mock_run):
        """TimeoutExpired should return False with a descriptive reason."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="vtysh", timeout=4)
        ok, details = self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertFalse(ok)
        self.assertIn("timed out", details["reason"].lower())

    @patch("src.policy.policy_engine.subprocess.run")
    def test_nonzero_returncode_returns_false(self, mock_run):
        """Non-zero vtysh exit code should return False."""
        mock_run.return_value = _make_proc("", returncode=1)
        ok, details = self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertFalse(ok)
        self.assertIn("non-zero", details["reason"].lower())

    @patch("src.policy.policy_engine.subprocess.run")
    def test_community_present_and_correct(self, mock_run):
        """When community is expected and present in RIB, should return True."""
        mock_run.return_value = _make_proc(RIB_WITH_COMMUNITY)
        ok, details = self.engine.verify_rib_best_path(
            "192.0.2.0/24", expected_lp=0, expected_community="no-export"
        )
        self.assertTrue(ok, msg=f"Expected True: {details}")

    @patch("src.policy.policy_engine.subprocess.run")
    def test_community_expected_but_absent_returns_false(self, mock_run):
        """When community is expected but missing from RIB community string, return False."""
        mock_run.return_value = _make_proc(RIB_MISSING_COMMUNITY)
        ok, details = self.engine.verify_rib_best_path(
            "192.0.2.0/24", expected_lp=0, expected_community="no-export"
        )
        self.assertFalse(ok)
        self.assertIn("community", details["reason"].lower())

    @patch("src.policy.policy_engine.subprocess.run")
    def test_no_community_expected_community_ignored(self, mock_run):
        """When expected_community=None, community field in RIB is not checked."""
        mock_run.return_value = _make_proc(DEFAULT_RIB_JSON)
        ok, details = self.engine.verify_rib_best_path(
            "192.0.2.0/24", expected_lp=80, expected_community=None
        )
        self.assertTrue(ok)

    @patch("src.policy.policy_engine.subprocess.run")
    def test_malformed_json_returns_false(self, mock_run):
        """Malformed JSON from vtysh should return False."""
        mock_run.return_value = _make_proc("not valid json")
        ok, details = self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertFalse(ok)
        self.assertIn("parse", details["reason"].lower())


if __name__ == "__main__":
    unittest.main()
