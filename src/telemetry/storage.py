"""
Full-Featured Telemetry Storage Engine with SQLite & JSONL support for Routes, Peers, System Metrics, and Convergence Events.
"""

import sqlite3
import json
import os
import time
from typing import Dict, Any, List, Optional
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
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS convergence_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        router_container TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        convergence_time_sec REAL NOT NULL,
                        target_prefix TEXT
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_route_pfx_time ON route_events(prefix, timestamp);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_route_router_time ON route_events(router_container, timestamp);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_peer_router_time ON bgp_peers(router_container, timestamp);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_container_time ON system_metrics(container_name, timestamp);")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite schema: {e}", exc_info=True)

    def write_route_events(self, events: List[Dict[str, Any]]):
        """Dual writes route telemetry to SQLite and JSONL."""
        if not events:
            return

        try:
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                for ev in events:
                    f.write(json.dumps(ev) + "\n")
        except Exception as e:
            logger.error(f"Failed writing to JSONL: {e}", exc_info=True)

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
            logger.error(f"Failed writing route events to SQLite: {e}", exc_info=True)

    def write_peer_events(self, peer_events: List[Dict[str, Any]]):
        """Writes BGP peer telemetry records to SQLite."""
        if not peer_events:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                records = [
                    (
                        pe.get("timestamp", time.time()),
                        pe.get("router_container", "unknown"),
                        pe.get("peer_ip", ""),
                        pe.get("remote_as", 0),
                        pe.get("state", ""),
                        pe.get("uptime", ""),
                        pe.get("prefixes_received", 0)
                    )
                    for pe in peer_events
                ]
                cursor.executemany("""
                    INSERT INTO bgp_peers 
                    (timestamp, router_container, peer_ip, remote_as, state, uptime, prefixes_received)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, records)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed writing peer events to SQLite: {e}", exc_info=True)

    def write_system_metrics(self, metrics: List[Dict[str, Any]]):
        """Writes CPU/RAM container metrics to SQLite."""
        if not metrics:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                records = [
                    (
                        m.get("timestamp", time.time()),
                        m.get("container_name", "unknown"),
                        m.get("cpu_percent", 0.0),
                        m.get("memory_mb", 0.0)
                    )
                    for m in metrics
                ]
                cursor.executemany("""
                    INSERT INTO system_metrics 
                    (timestamp, container_name, cpu_percent, memory_mb)
                    VALUES (?, ?, ?, ?)
                """, records)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed writing system metrics to SQLite: {e}", exc_info=True)

    def write_convergence_event(self, router: str, event_type: str, convergence_sec: float, target_prefix: str = ""):
        """Records a BGP convergence timing event."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO convergence_events
                    (timestamp, router_container, event_type, convergence_time_sec, target_prefix)
                    VALUES (?, ?, ?, ?, ?)
                """, (time.time(), router, event_type, convergence_sec, target_prefix))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed writing convergence event to SQLite: {e}", exc_info=True)
