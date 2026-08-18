"""
Resilient FRRouting Telemetry Collector with Real RIB Transition Tracking,
Configured Peer Denominator, and System Metrics Profiling.
"""

import json
import subprocess
import time
import os
import psutil
from typing import Dict, Any, List, Optional
from src.utils.logger import setup_logger
from src.telemetry.buffer import SlidingWindowBuffer
from src.telemetry.storage import TelemetryStorage

logger = setup_logger("frr_collector")

class FRRTelemetryCollector:
    def __init__(self, router_container: str = "as65003", poll_interval: float = 1.0,
                 buffer_window_size: int = 100, buffer_time_window_sec: float = 300.0,
                 total_configured_peers: int = 2):
        self.router_container = router_container
        self.poll_interval = poll_interval
        self.buffer = SlidingWindowBuffer(window_size=buffer_window_size, time_window_seconds=buffer_time_window_sec)
        self.storage = TelemetryStorage()
        self.previous_rib: Dict[str, Dict[str, Any]] = {}
        self.total_configured_peers = total_configured_peers
        self.established_peers_count = 0

    def exec_vtysh_json(self, command: str) -> Optional[Dict[str, Any]]:
        """Executes vtysh command returning parsed JSON with exponential retry."""
        for attempt in range(1, 4):
            try:
                res = subprocess.run(
                    ["docker", "exec", self.router_container, "vtysh", "-c", command],
                    capture_output=True,
                    text=True,
                    timeout=4
                )
                if res.returncode == 0 and res.stdout.strip():
                    return json.loads(res.stdout)
            except Exception:
                time.sleep(0.1 * (2 ** attempt))
        return None

    def collect_bgp_summary(self) -> Dict[str, Any]:
        """Collects peer state, logs peer records, and updates established peer count."""
        data = self.exec_vtysh_json("show bgp summary json")
        if not data:
            return {}

        ipv4_peers = data.get("ipv4Unicast", {}).get("peers", {})
        active_count = 0
        peer_records = []
        now = time.time()

        for peer_ip, pinfo in ipv4_peers.items():
            state = pinfo.get("state", "")
            if state.lower() == "established":
                active_count += 1
            peer_records.append({
                "timestamp": now,
                "router_container": self.router_container,
                "peer_ip": peer_ip,
                "remote_as": pinfo.get("remoteAs", 0),
                "state": state,
                "uptime": str(pinfo.get("peerUptime", "")),
                "prefixes_received": pinfo.get("pfxRcd", 0)
            })

        self.established_peers_count = active_count
        if peer_records:
            self.storage.write_peer_events(peer_records)

        return ipv4_peers

    def collect_system_metrics(self) -> Dict[str, Any]:
        """Collects CPU and Memory utilization for container host and processes."""
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().used / (1024 * 1024)
        record = [{
            "timestamp": time.time(),
            "container_name": self.router_container,
            "cpu_percent": cpu,
            "memory_mb": round(mem, 2)
        }]
        self.storage.write_system_metrics(record)
        return record[0]

    def verify_nexthop_reachability(self, nexthop_ip: str) -> bool:
        """Verifies if the specified next-hop IP is reachable and established in FRR."""
        summary = self.collect_bgp_summary()
        if nexthop_ip in summary:
            return summary[nexthop_ip].get("state", "").lower() == "established"
        return True

    def collect_route_rib(self) -> Dict[str, Any]:
        """
        Collects full BGP RIB, detects actual RIB transitions against previous_rib,
        and populates sliding-window buffers.
        """
        data = self.exec_vtysh_json("show bgp ipv4 unicast json")
        if not data:
            return {"routes": [], "transitions": []}

        routes_dict = data.get("routes", {})
        parsed_routes = []
        current_best_rib: Dict[str, Dict[str, Any]] = {}
        transitions = []
        now = time.time()

        for prefix, path_list in routes_dict.items():
            if not isinstance(path_list, list):
                path_list = [path_list]

            distinct_nexthops = set()
            for path in path_list:
                distinct_nexthops.add(path.get("nexthop", ""))

                aspath_obj = path.get("aspath", {})
                aspath_str = aspath_obj.get("string", "") if isinstance(aspath_obj, dict) else str(aspath_obj)
                
                tokens = aspath_str.split()
                origin_as = int(tokens[-1]) if tokens and tokens[-1].isdigit() else 0

                last_update = path.get("lastUpdate", 0)
                if isinstance(last_update, (int, float)) and last_update > 1000000:
                    last_update_epoch = float(last_update)
                else:
                    last_update_epoch = now

                route_record = {
                    "timestamp": now,
                    "router_container": self.router_container,
                    "prefix": prefix,
                    "nexthop": path.get("nexthop", ""),
                    "as_path": aspath_str,
                    "origin_as": origin_as,
                    "loc_pref": path.get("locPrf", 100) or 100,
                    "med": path.get("metric", 0) or 0,
                    "community": path.get("community", {}).get("string", "") if isinstance(path.get("community"), dict) else "",
                    "is_best": path.get("bestpath", False),
                    "last_update_epoch": last_update_epoch,
                    "active_neighbors": len(distinct_nexthops)
                }

                if route_record["is_best"]:
                    parsed_routes.append(route_record)
                    current_best_rib[prefix] = route_record
                    self.buffer.add_event(prefix, route_record)

                    # Track RIB state transition against previous snapshot
                    prev = self.previous_rib.get(prefix)
                    if not prev:
                        transitions.append({"prefix": prefix, "type": "NEW_ANNOUNCEMENT", "route": route_record})
                    elif prev.get("as_path") != aspath_str or prev.get("origin_as") != origin_as:
                        transitions.append({"prefix": prefix, "type": "PATH_ATTRIBUTE_CHANGE", "route": route_record, "prev": prev})

        # Detect withdrawals
        for pfx, prev_route in self.previous_rib.items():
            if pfx not in current_best_rib:
                transitions.append({"prefix": pfx, "type": "ROUTE_WITHDRAWAL", "route": prev_route})

        self.previous_rib = current_best_rib

        if parsed_routes:
            self.storage.write_route_events(parsed_routes)

        return {"routes": parsed_routes, "transitions": transitions}
