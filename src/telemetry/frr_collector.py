"""
Resilient FRRouting Telemetry Collector with Real RIB Transition Tracking,
Configured Peer Denominator, and System Metrics Profiling.
Async-enabled using safe non-blocking subprocess execution.
"""

import json
import time
import asyncio
import psutil
from typing import Dict, Any, List, Optional
from src.utils.logger import setup_logger
from src.utils.async_utils import run_subprocess_async
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
        self._last_peer_summary: Dict[str, Any] = {}

    async def exec_vtysh_json(self, command: str) -> Optional[Dict[str, Any]]:
        """Executes vtysh command asynchronously returning parsed JSON with exponential retry."""
        for attempt in range(1, 4):
            try:
                rc, stdout, _ = await run_subprocess_async(
                    "docker", "exec", self.router_container, "vtysh", "-c", command,
                    timeout=4.0
                )
                if rc == 0 and stdout.strip():
                    return json.loads(stdout.decode())
            except asyncio.TimeoutError:
                logger.warning(f"[{self.router_container}] vtysh command timed out (attempt {attempt}/3): {command}")
                await asyncio.sleep(0.1 * (2 ** attempt))
            except Exception as e:
                logger.warning(f"[{self.router_container}] vtysh command failed (attempt {attempt}/3): {e}")
                await asyncio.sleep(0.1 * (2 ** attempt))
        return None

    async def collect_bgp_summary(self) -> Dict[str, Any]:
        """Collects peer state, logs peer records, updates established peer count and caches peer summary."""
        data = await self.exec_vtysh_json("show bgp summary json")
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
        self._last_peer_summary = ipv4_peers.copy()

        if peer_records:
            await self.storage.write_peer_events(peer_records)

        return ipv4_peers

    def check_cached_reachability(self, peer_ip: str) -> bool:
        """Synchronously checks reachability of peer_ip from cached summary without calling Docker."""
        if not self._last_peer_summary:
            return True
        if peer_ip in self._last_peer_summary:
            return self._last_peer_summary[peer_ip].get("state", "").lower() == "established"
        return True

    async def verify_nexthop_reachability(self, nexthop_ip: str) -> bool:
        """Verifies if the specified next-hop IP is reachable and established in FRR."""
        summary = await self.collect_bgp_summary()
        if nexthop_ip in summary:
            return summary[nexthop_ip].get("state", "").lower() == "established"
        return True

    async def collect_system_metrics(self) -> Dict[str, Any]:
        """Collects CPU and Memory utilization asynchronously."""
        cpu = await asyncio.to_thread(psutil.cpu_percent, interval=None)
        mem_used = await asyncio.to_thread(lambda: psutil.virtual_memory().used / (1024 * 1024))
        record = [{
            "timestamp": time.time(),
            "container_name": self.router_container,
            "cpu_percent": cpu,
            "memory_mb": round(mem_used, 2)
        }]
        await self.storage.write_system_metrics(record)
        return record[0]

    async def collect_snapshot(self, snapshot_id: int) -> Dict[str, Any]:
        """
        Atomically collects full BGP RIB and each prefix's sliding window history.
        Guarantees that routes and histories belong to the exact same snapshot moment.
        """
        data = await self.exec_vtysh_json("show bgp ipv4 unicast json")
        collected_at = time.monotonic()
        if not data:
            return {
                "snapshot_id": snapshot_id,
                "collected_at": collected_at,
                "routes_with_history": [],
                "transitions": []
            }

        routes_dict = data.get("routes", {})
        routes_with_history = []
        current_best_rib: Dict[str, Dict[str, Any]] = {}
        transitions = []
        now = time.time()

        for prefix, path_list in routes_dict.items():
            if not isinstance(path_list, list):
                path_list = [path_list]

            distinct_nexthops = set()
            for path in path_list:
                for nh in path.get("nexthops", []):
                    if isinstance(nh, dict) and nh.get("ip"):
                        distinct_nexthops.add(nh["ip"])
                nexthop_ip = path.get("nexthop", "")
                if not nexthop_ip and path.get("nexthops"):
                    nexthop_ip = path["nexthops"][0].get("ip", "")
                if nexthop_ip:
                    distinct_nexthops.add(nexthop_ip)

                aspath_val = path.get("path") if path.get("path") is not None else path.get("aspath", {})
                if isinstance(aspath_val, dict):
                    aspath_str = aspath_val.get("string", "")
                else:
                    aspath_str = str(aspath_val or "").strip()
                
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
                    self.buffer.add_event(prefix, route_record)
                    history = self.buffer.get_history_for(prefix)
                    routes_with_history.append({
                        "route": route_record,
                        "history": history
                    })
                    current_best_rib[prefix] = route_record

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

        if routes_with_history:
            await self.storage.write_route_events([item["route"] for item in routes_with_history])

        return {
            "snapshot_id": snapshot_id,
            "collected_at": collected_at,
            "routes_with_history": routes_with_history,
            "transitions": transitions
        }

    async def collect_route_rib(self) -> Dict[str, Any]:
        """Backward-compatible helper that collects snapshot and returns routes and transitions."""
        snapshot = await self.collect_snapshot(snapshot_id=0)
        return {
            "routes": [item["route"] for item in snapshot["routes_with_history"]],
            "transitions": snapshot["transitions"]
        }
