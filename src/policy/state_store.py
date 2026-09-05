"""
SQLite-backed Persistent Controller State Store with asyncio.to_thread support.
Persists active policy overrides, classifications, and trust history across controller restarts.
Also records detection and mitigation timestamps for live MTTD/MTTM measurement.
"""

import sqlite3
import os
import time
import asyncio
import contextlib
from typing import Dict, Any, Optional

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
DB_PATH = os.path.join(DB_DIR, "controller_state.db")

class ControllerStateStore:
    def __init__(self, db_path: Optional[str] = None, router_name: str = "default"):
        if db_path is None:
            if router_name == "default":
                self.db_path = DB_PATH
            else:
                self.db_path = os.path.join(DB_DIR, f"controller_state_{router_name}.db")
        else:
            self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._db_lock = asyncio.Lock()

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

    def _init_db_sync(self):
        with self._get_connection() as conn:
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

    async def initialize(self) -> None:
        """Explicitly awaitable database initializer."""
        await asyncio.to_thread(self._init_db_sync)

    # ------------------------------------------------------------------
    # Synchronous private implementations
    # ------------------------------------------------------------------

    def _save_policy_sync(self, prefix: str, loc_pref: int, community: Optional[str],
                          classification_id: int, trust_score: float, verified: bool = False):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO active_policies
                (prefix, loc_pref, community, classification_id, trust_score, applied_at, verified_in_frr)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (prefix, loc_pref, community, classification_id, trust_score,
                  time.time(), 1 if verified else 0))

    def _remove_policy_sync(self, prefix: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM active_policies WHERE prefix = ?", (prefix,))

    def _get_all_active_policies_sync(self) -> Dict[str, Dict[str, Any]]:
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

    def _record_detection_sync(self, prefix: str, class_id: int, trust_score: float) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO detection_events (prefix, detected_at, class_id, trust_score)
                VALUES (?, ?, ?, ?)
                """,
                (prefix, time.time(), class_id, trust_score)
            )
            return cursor.lastrowid

    def _record_mitigation_sync(self, prefix: str) -> bool:
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

    def _get_latest_detection_sync(self, prefix: str) -> Optional[Dict[str, Any]]:
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

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def save_policy(self, prefix: str, loc_pref: int, community: Optional[str],
                          classification_id: int, trust_score: float, verified: bool = False):
        async with self._db_lock:
            await asyncio.to_thread(
                self._save_policy_sync, prefix, loc_pref, community, classification_id, trust_score, verified
            )

    async def remove_policy(self, prefix: str):
        async with self._db_lock:
            await asyncio.to_thread(self._remove_policy_sync, prefix)

    async def get_all_active_policies(self) -> Dict[str, Dict[str, Any]]:
        return await asyncio.to_thread(self._get_all_active_policies_sync)

    async def record_detection(self, prefix: str, class_id: int, trust_score: float) -> int:
        async with self._db_lock:
            return await asyncio.to_thread(self._record_detection_sync, prefix, class_id, trust_score)

    async def record_mitigation(self, prefix: str) -> bool:
        async with self._db_lock:
            return await asyncio.to_thread(self._record_mitigation_sync, prefix)

    async def get_latest_detection(self, prefix: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._get_latest_detection_sync, prefix)
