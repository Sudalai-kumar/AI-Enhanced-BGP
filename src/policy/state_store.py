"""
SQLite-backed Persistent Controller State Store.
Persists active policy overrides, classifications, and trust history across controller restarts.
"""

import sqlite3
import os
import time
from typing import Dict, Any, Optional

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
DB_PATH = os.path.join(DB_DIR, "controller_state.db")

class ControllerStateStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
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
            conn.commit()

    def save_policy(self, prefix: str, loc_pref: int, community: Optional[str],
                    classification_id: int, trust_score: float, verified: bool = False):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO active_policies 
                (prefix, loc_pref, community, classification_id, trust_score, applied_at, verified_in_frr)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (prefix, loc_pref, community, classification_id, trust_score, time.time(), 1 if verified else 0))
            conn.commit()

    def remove_policy(self, prefix: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM active_policies WHERE prefix = ?", (prefix,))
            conn.commit()

    def get_all_active_policies(self) -> Dict[str, Dict[str, Any]]:
        policies = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT prefix, loc_pref, community, classification_id, trust_score, applied_at, verified_in_frr FROM active_policies")
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
