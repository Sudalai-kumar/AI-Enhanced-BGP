"""
SQLite and JSONL Telemetry Storage Engine with Safe Exception Handling & Schema Indexes.
"""

import sqlite3
import json
import os
import time
from typing import Dict, Any, List
from src.utils.logger import setup_logger

logger = setup_logger("telemetry_storage")

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
RAW_DIR = os.path.join(DB_DIR, "raw")
DB_PATH = os.path.join(DB_DIR, "telemetry.db")
JSONL_PATH = os.path.join(RAW_DIR, "bgp_telemetry.jsonl")

class TelemetryStorage:
    def __init__(self, db_path: str = DB_PATH, jsonl_path: str = JSONL_PATH):
        self.db_path = db_path
        self.jsonl_path = jsonl_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.jsonl_path), exist_ok=True)
        self._init_sqlite()

    def _init_sqlite(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS route_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        router_container TEXT NOT NULL,
                        prefix TEXT NOT NULL,
                        nexthop TEXT,
                        as_path TEXT,
                        origin_as INTEGER,
                        loc_pref INTEGER,
                        med INTEGER,
                        community TEXT,
                        is_best INTEGER,
                        last_update_epoch REAL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bgp_peers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        router_container TEXT NOT NULL,
                        peer_ip TEXT NOT NULL,
                        remote_as INTEGER,
                        state TEXT,
                        uptime TEXT,
                        prefixes_received INTEGER
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        container_name TEXT NOT NULL,
                        cpu_percent REAL,
                        memory_mb REAL
                    )
                """)
                # Create Performance Indexes for Week 9-10 Multi-iteration Queries
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_route_pfx_time ON route_events(prefix, timestamp);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_route_router_time ON route_events(router_container, timestamp);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_peer_router_time ON bgp_peers(router_container, timestamp);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_container_time ON system_metrics(container_name, timestamp);")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite schema: {e}", exc_info=True)

    def write_route_events(self, events: List[Dict[str, Any]]):
        """Dual writes route telemetry to SQLite and JSONL with robust error logging."""
        if not events:
            return

        # 1. JSONL Write
        try:
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                for ev in events:
                    f.write(json.dumps(ev) + "\n")
        except Exception as e:
            logger.error(f"Failed writing to JSONL: {e}", exc_info=True)

        # 2. SQLite Write
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                records = [
                    (
                        ev.get("timestamp", time.time()),
                        ev.get("router_container", "unknown"),
                        ev.get("prefix", ""),
                        ev.get("nexthop", ""),
                        ev.get("as_path", ""),
                        ev.get("origin_as", 0),
                        ev.get("loc_pref", 100),
                        ev.get("med", 0),
                        ev.get("community", ""),
                        1 if ev.get("is_best", True) else 0,
                        ev.get("last_update_epoch", 0.0)
                    )
                    for ev in events
                ]
                cursor.executemany("""
                    INSERT INTO route_events 
                    (timestamp, router_container, prefix, nexthop, as_path, origin_as, loc_pref, med, community, is_best, last_update_epoch)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, records)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed writing to SQLite DB: {e}", exc_info=True)
