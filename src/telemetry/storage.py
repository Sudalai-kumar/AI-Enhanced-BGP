"""
Time-series and Telemetry Data Storage Engine.
Provides dual persistence:
1. Append-only JSON Lines (.jsonl) for raw event streams and streaming ML replay.
2. Structured SQLite (.db) for rapid relational indexing, query evaluation, and metric computation.
"""

import json
import sqlite3
import os
import time
from typing import Dict, Any, List, Optional

class TelemetryStorage:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.raw_dir = os.path.join(data_dir, "raw")
        self.db_path = os.path.join(data_dir, "telemetry.db")
        self.jsonl_path = os.path.join(self.raw_dir, "bgp_telemetry.jsonl")
        
        os.makedirs(self.raw_dir, exist_ok=True)
        self._init_sqlite()

    def _init_sqlite(self):
        """Initializes SQLite tables for BGP events, route metrics, and system metrics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Table: BGP Peers & Sessions
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS bgp_peers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                router_name TEXT,
                peer_ip TEXT,
                remote_as INTEGER,
                state TEXT,
                uptime_str TEXT,
                pfx_rcvd INTEGER,
                pfx_sent INTEGER
            )
            """)
            
            # Table: Route Rib Entries
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS route_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                router_name TEXT,
                prefix TEXT,
                nexthop TEXT,
                as_path TEXT,
                origin_as INTEGER,
                as_path_len INTEGER,
                loc_pref INTEGER,
                med INTEGER,
                is_best INTEGER,
                status_code TEXT
            )
            """)
            
            # Table: System Telemetry (CPU / Memory)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                container_name TEXT,
                cpu_perc TEXT,
                mem_usage TEXT,
                mem_perc TEXT,
                pids TEXT
            )
            """)
            
            # Table: Baseline Latency and Anomaly Events
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS convergence_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                event_type TEXT,
                affected_prefix TEXT,
                convergence_duration_sec REAL,
                details TEXT
            )
            """)
            
            conn.commit()

    def log_event(self, record: Dict[str, Any]):
        """Dual-writes record to JSONL and SQLite."""
        # 1. JSON Lines
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
            
        # 2. SQLite
        record_type = record.get("record_type")
        timestamp = record.get("timestamp", time.time())
        router_name = record.get("router", "unknown")
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if record_type == "peer_summary":
                    for peer in record.get("peers", []):
                        cursor.execute("""
                            INSERT INTO bgp_peers 
                            (timestamp, router_name, peer_ip, remote_as, state, uptime_str, pfx_rcvd, pfx_sent)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            timestamp,
                            router_name,
                            peer.get("peer_ip"),
                            peer.get("remote_as"),
                            peer.get("state"),
                            peer.get("uptime"),
                            peer.get("pfx_rcvd", 0),
                            peer.get("pfx_sent", 0)
                        ))
                elif record_type == "route_rib":
                    for route in record.get("routes", []):
                        cursor.execute("""
                            INSERT INTO route_events
                            (timestamp, router_name, prefix, nexthop, as_path, origin_as, as_path_len, loc_pref, med, is_best, status_code)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            timestamp,
                            router_name,
                            route.get("prefix"),
                            route.get("nexthop"),
                            route.get("as_path"),
                            route.get("origin_as"),
                            route.get("as_path_len", 0),
                            route.get("loc_pref", 100),
                            route.get("med", 0),
                            1 if route.get("is_best") else 0,
                            route.get("status_code", "")
                        ))
                elif record_type == "system_metric":
                    stats = record.get("stats", {})
                    cursor.execute("""
                        INSERT INTO system_metrics
                        (timestamp, container_name, cpu_perc, mem_usage, mem_perc, pids)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        timestamp,
                        stats.get("container", router_name),
                        stats.get("cpu_perc"),
                        stats.get("mem_usage"),
                        stats.get("mem_perc"),
                        stats.get("pids")
                    ))
                elif record_type == "convergence_metric":
                    cursor.execute("""
                        INSERT INTO convergence_events
                        (timestamp, event_type, affected_prefix, convergence_duration_sec, details)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        timestamp,
                        record.get("event_type"),
                        record.get("prefix"),
                        record.get("duration"),
                        json.dumps(record.get("details", {}))
                    ))
                conn.commit()
        except Exception as e:
            # Fallback error logger
            pass
