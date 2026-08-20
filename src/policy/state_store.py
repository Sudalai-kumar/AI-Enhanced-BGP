"""
SQLite-backed Persistent Controller State Store.
Persists active policy overrides, classifications, and trust history across controller restarts.
Also records detection and mitigation timestamps for live MTTD/MTTM measurement.
"""

import sqlite3
import os
import time
import contextlib
from typing import Dict, Any, Optional

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
DB_PATH = os.path.join(DB_DIR, "controller_state.db")

class ControllerStateStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            # Table 1: active policy overrides (unchanged)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS active_policies (
                    prefix TEXT PRIMARY KEY,
                    loc_pref INTEGER NOT NULL,
                    community TEXT,
                    classification_id INTEGER NOT NULL,
                    trust_score REAL NOT NULL,
                    applied_at REAL NOT NULL,
                    verified_in_frr INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_active_pfx ON active_policies(prefix);")

            # Table 2: detection and mitigation event log for live MTTD/MTTM measurement.
            # detected_at  -- epoch seconds when the controller first classifies the prefix
            #                 as anomalous and promotes it out of the shadow queue.
            # mitigated_at -- epoch seconds when apply_policy() succeeds for this event;
            #                 NULL until mitigation is confirmed.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS detection_events (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    prefix       TEXT    NOT NULL,
                    detected_at  REAL    NOT NULL,
                    class_id     INTEGER NOT NULL,
                    trust_score  REAL    NOT NULL,
                    mitigated_at REAL    DEFAULT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_det_prefix "
                "ON detection_events(prefix, detected_at);"
            )

    # ------------------------------------------------------------------
    # Active policy methods (unchanged behaviour)
    # ------------------------------------------------------------------

    def save_policy(self, prefix: str, loc_pref: int, community: Optional[str],
                    classification_id: int, trust_score: float, verified: bool = False):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO active_policies
                (prefix, loc_pref, community, classification_id, trust_score, applied_at, verified_in_frr)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (prefix, loc_pref, community, classification_id, trust_score,
                  time.time(), 1 if verified else 0))

    def remove_policy(self, prefix: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM active_policies WHERE prefix = ?", (prefix,))

    def get_all_active_policies(self) -> Dict[str, Dict[str, Any]]:
        policies = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT prefix, loc_pref, community, classification_id, "
                "trust_score, applied_at, verified_in_frr FROM active_policies"
            )
            for row in cursor.fetchall():
                policies[row[0]] = {
                    "loc_pref": row[1],
                    "community": row[2],
                    "classification_id": row[3],
                    "trust_score": row[4],
                    "applied_at": row[5],
                    "verified_in_frr": bool(row[6])
                }
        return policies

    # ------------------------------------------------------------------
    # Detection event methods (new — used for live MTTD/MTTM measurement)
    # ------------------------------------------------------------------

    def record_detection(self, prefix: str, class_id: int, trust_score: float) -> int:
        """
        Records the moment the controller first promotes a shadow-staged anomaly to
        live action.  Inserts a new row with detected_at=now, mitigated_at=NULL.

        Returns the new row's id so the caller can correlate it with record_mitigation.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO detection_events (prefix, detected_at, class_id, trust_score)
                VALUES (?, ?, ?, ?)
                """,
                (prefix, time.time(), class_id, trust_score)
            )
            return cursor.lastrowid

    def record_mitigation(self, prefix: str) -> bool:
        """
        Stamps mitigated_at=now on the most recent open (mitigated_at IS NULL)
        detection row for the given prefix.

        Returns True if a row was updated, False if no open row was found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE detection_events
                SET    mitigated_at = ?
                WHERE  prefix = ?
                  AND  mitigated_at IS NULL
                  AND  id = (
                        SELECT id FROM detection_events
                        WHERE  prefix = ? AND mitigated_at IS NULL
                        ORDER  BY detected_at DESC
                        LIMIT  1
                  )
                """,
                (time.time(), prefix, prefix)
            )
            return cursor.rowcount > 0

    def get_latest_detection(self, prefix: str) -> Optional[Dict[str, Any]]:
        """
        Returns the most recent detection_events row for prefix as a dict,
        or None if no row exists.

        Fields: id, prefix, detected_at, class_id, trust_score, mitigated_at
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, prefix, detected_at, class_id, trust_score, mitigated_at
                FROM   detection_events
                WHERE  prefix = ?
                ORDER  BY detected_at DESC
                LIMIT  1
                """,
                (prefix,)
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "prefix": row[1],
                "detected_at": row[2],
                "class_id": row[3],
                "trust_score": row[4],
                "mitigated_at": row[5],
            }
