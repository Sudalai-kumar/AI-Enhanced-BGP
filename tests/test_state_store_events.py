"""
Unit tests for the detection_events table in ControllerStateStore.
All tests use an in-memory SQLite path (":memory:") so no files are created.
"""

import time
import sqlite3
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.policy.state_store import ControllerStateStore


class TestDetectionEventsTable(unittest.TestCase):

    def setUp(self):
        # Use a temporary file per test to avoid cross-test leakage
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmpdir, "test_ctrl.db")
        self.store = ControllerStateStore(db_path=self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # record_detection
    # ------------------------------------------------------------------

    def test_record_detection_creates_row(self):
        """record_detection should insert a row with mitigated_at=None."""
        row_id = self.store.record_detection(
            prefix="192.0.2.0/24", class_id=3, trust_score=0.10
        )
        self.assertIsNotNone(row_id)
        self.assertGreater(row_id, 0)

        row = self.store.get_latest_detection("192.0.2.0/24")
        self.assertIsNotNone(row)
        self.assertEqual(row["prefix"], "192.0.2.0/24")
        self.assertEqual(row["class_id"], 3)
        self.assertAlmostEqual(row["trust_score"], 0.10, places=3)
        self.assertIsNone(row["mitigated_at"],
                          msg="mitigated_at should be NULL before record_mitigation is called")

    def test_record_detection_detected_at_is_recent(self):
        """detected_at should be close to the current epoch time."""
        before = time.time()
        self.store.record_detection("192.0.2.0/24", class_id=1, trust_score=0.55)
        after = time.time()
        row = self.store.get_latest_detection("192.0.2.0/24")
        self.assertGreaterEqual(row["detected_at"], before)
        self.assertLessEqual(row["detected_at"], after)

    # ------------------------------------------------------------------
    # record_mitigation
    # ------------------------------------------------------------------

    def test_record_mitigation_fills_timestamp(self):
        """record_mitigation should set mitigated_at on the open row."""
        self.store.record_detection("192.0.2.0/24", class_id=3, trust_score=0.05)
        updated = self.store.record_mitigation("192.0.2.0/24")
        self.assertTrue(updated, msg="record_mitigation should return True when a row was updated")
        row = self.store.get_latest_detection("192.0.2.0/24")
        self.assertIsNotNone(row["mitigated_at"],
                             msg="mitigated_at should be set after record_mitigation")

    def test_record_mitigation_returns_false_with_no_open_row(self):
        """record_mitigation should return False when no open detection exists."""
        updated = self.store.record_mitigation("10.0.0.0/8")
        self.assertFalse(updated)

    def test_record_mitigation_only_updates_open_row(self):
        """After mitigation, calling record_mitigation again should return False."""
        self.store.record_detection("192.0.2.0/24", class_id=3, trust_score=0.05)
        self.store.record_mitigation("192.0.2.0/24")  # closes the row
        updated_again = self.store.record_mitigation("192.0.2.0/24")
        self.assertFalse(updated_again,
                         msg="Second call should find no open row and return False")

    # ------------------------------------------------------------------
    # get_latest_detection
    # ------------------------------------------------------------------

    def test_get_latest_detection_returns_most_recent(self):
        """With multiple rows, get_latest_detection returns the newest."""
        self.store.record_detection("192.0.2.0/24", class_id=1, trust_score=0.60)
        time.sleep(0.01)  # ensure distinct timestamps
        self.store.record_detection("192.0.2.0/24", class_id=3, trust_score=0.10)
        row = self.store.get_latest_detection("192.0.2.0/24")
        self.assertEqual(row["class_id"], 3,
                         msg="Should return the most recent row (class_id=3)")

    def test_get_latest_detection_returns_none_for_unknown_prefix(self):
        """get_latest_detection should return None for an unrecorded prefix."""
        row = self.store.get_latest_detection("1.2.3.4/32")
        self.assertIsNone(row)

    # ------------------------------------------------------------------
    # MTTD / MTTM ordering invariant
    # ------------------------------------------------------------------

    def test_mitigated_at_gte_detected_at(self):
        """mitigated_at must always be >= detected_at (mitigation cannot precede detection)."""
        self.store.record_detection("192.0.2.0/24", class_id=3, trust_score=0.05)
        time.sleep(0.01)  # ensure separation
        self.store.record_mitigation("192.0.2.0/24")
        row = self.store.get_latest_detection("192.0.2.0/24")
        self.assertGreaterEqual(
            row["mitigated_at"], row["detected_at"],
            msg="mitigated_at must be >= detected_at"
        )

    # ------------------------------------------------------------------
    # active_policies table not affected
    # ------------------------------------------------------------------

    def test_detection_events_independent_of_active_policies(self):
        """detection_events and active_policies are independent tables."""
        self.store.save_policy(
            "192.0.2.0/24", loc_pref=0, community="no-export",
            classification_id=3, trust_score=0.05, verified=True
        )
        self.store.record_detection("192.0.2.0/24", class_id=3, trust_score=0.05)
        # Removing the active policy must not affect detection_events
        self.store.remove_policy("192.0.2.0/24")
        row = self.store.get_latest_detection("192.0.2.0/24")
        self.assertIsNotNone(row, msg="Detection event should survive removal of active policy")


if __name__ == "__main__":
    unittest.main()
