"""
Unit tests for BGPPolicyEngine.verify_rib_best_path() (Async-enabled).
All tests mock run_subprocess_async so no Docker is required.
"""

import json
import asyncio
import unittest
from unittest.mock import patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.policy.policy_engine import BGPPolicyEngine


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


class TestVerifyRIBBestPath(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.engine = BGPPolicyEngine(router="as65003", peer_ip="10.0.23.2")

    @patch("src.policy.policy_engine.run_subprocess_async")
    async def test_correct_best_path_returns_true(self, mock_run):
        """Correct LP in RIB should return True."""
        mock_run.return_value = (0, DEFAULT_RIB_JSON.encode(), b"")
        ok, details = await self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertTrue(ok, msg=f"Expected True but got False: {details}")
        self.assertEqual(details["reason"], "OK")

    @patch("src.policy.policy_engine.run_subprocess_async")
    async def test_wrong_lp_in_rib_returns_false(self, mock_run):
        """If FRR RIB shows different LP than expected, should return False."""
        mock_run.return_value = (0, RIB_WRONG_LP.encode(), b"")
        ok, details = await self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertFalse(ok)
        self.assertIn("mismatch", details["reason"].lower())
        self.assertEqual(details["actual_lp"], 100)

    @patch("src.policy.policy_engine.run_subprocess_async")
    async def test_prefix_not_in_rib_returns_false(self, mock_run):
        """Empty paths list should return False."""
        mock_run.return_value = (0, RIB_NO_PATHS.encode(), b"")
        ok, details = await self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertFalse(ok)
        self.assertIn("No paths", details["reason"])

    @patch("src.policy.policy_engine.run_subprocess_async")
    async def test_timeout_returns_false(self, mock_run):
        """TimeoutError should return False with a descriptive reason."""
        mock_run.side_effect = asyncio.TimeoutError()
        ok, details = await self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertFalse(ok)
        self.assertIn("timed out", details["reason"].lower())

    @patch("src.policy.policy_engine.run_subprocess_async")
    async def test_nonzero_returncode_returns_false(self, mock_run):
        """Non-zero vtysh exit code should return False."""
        mock_run.return_value = (1, b"", b"")
        ok, details = await self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertFalse(ok)
        self.assertIn("non-zero", details["reason"].lower())

    @patch("src.policy.policy_engine.run_subprocess_async")
    async def test_community_present_and_correct(self, mock_run):
        """When community is expected and present in RIB, should return True."""
        mock_run.return_value = (0, RIB_WITH_COMMUNITY.encode(), b"")
        ok, details = await self.engine.verify_rib_best_path(
            "192.0.2.0/24", expected_lp=0, expected_community="no-export"
        )
        self.assertTrue(ok, msg=f"Expected True: {details}")

    @patch("src.policy.policy_engine.run_subprocess_async")
    async def test_community_expected_but_absent_returns_false(self, mock_run):
        """When community is expected but missing from RIB community string, return False."""
        mock_run.return_value = (0, RIB_MISSING_COMMUNITY.encode(), b"")
        ok, details = await self.engine.verify_rib_best_path(
            "192.0.2.0/24", expected_lp=0, expected_community="no-export"
        )
        self.assertFalse(ok)
        self.assertIn("community", details["reason"].lower())

    @patch("src.policy.policy_engine.run_subprocess_async")
    async def test_no_community_expected_community_ignored(self, mock_run):
        """When expected_community=None, community field in RIB is not checked."""
        mock_run.return_value = (0, DEFAULT_RIB_JSON.encode(), b"")
        ok, details = await self.engine.verify_rib_best_path(
            "192.0.2.0/24", expected_lp=80, expected_community=None
        )
        self.assertTrue(ok)

    @patch("src.policy.policy_engine.run_subprocess_async")
    async def test_malformed_json_returns_false(self, mock_run):
        """Malformed JSON from vtysh should return False."""
        mock_run.return_value = (0, b"not valid json", b"")
        ok, details = await self.engine.verify_rib_best_path("192.0.2.0/24", expected_lp=80)
        self.assertFalse(ok)
        self.assertIn("parse", details["reason"].lower())


if __name__ == "__main__":
    unittest.main()
