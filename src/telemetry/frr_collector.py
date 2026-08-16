"""
Resilient FRRouting (FRR) Telemetry Collector.
Polls FRR nodes via vtysh, parses JSON telemetry with exponential-backoff retry logic,
and feeds both in-memory buffers and persistent storage (JSONL + SQLite).
"""

import subprocess
import json
import time
import argparse
from typing import Dict, Any, List, Optional
from src.utils.logger import setup_logger
from src.utils.system_metrics import get_container_stats
from src.telemetry.buffer import SlidingWindowBuffer
from src.telemetry.storage import TelemetryStorage

logger = setup_logger("frr_collector")

class FRRTelemetryCollector:
    def __init__(self, router_container: str = "as65003", poll_interval: float = 2.0, storage: Optional[TelemetryStorage] = None):
        self.router = router_container
        self.interval = poll_interval
        self.storage = storage or TelemetryStorage()
        self.buffer = SlidingWindowBuffer()
        self.running = False

    def exec_vtysh_json(self, command: str, max_retries: int = 3, initial_delay: float = 0.5) -> Optional[Dict[str, Any]]:
        """
        Executes a vtysh command inside the FRR container and parses JSON output.
        Applies exponential backoff for resilience during routing transitions.
        """
        delay = initial_delay
        full_cmd = ["docker", "exec", self.router, "vtysh", "-c", f"{command} json"]
        
        for attempt in range(1, max_retries + 1):
            try:
                res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=6)
                if res.returncode == 0 and res.stdout.strip():
                    raw_text = res.stdout.strip()
                    try:
                        return json.loads(raw_text)
                    except json.JSONDecodeError:
                        logger.warning(f"[{self.router}] Malformed JSON on attempt {attempt}/{max_retries} for '{command}'. Retrying in {delay}s...")
                else:
                    logger.debug(f"[{self.router}] Non-zero exit code or empty output on attempt {attempt}/{max_retries}: {res.stderr.strip()}")
            except subprocess.TimeoutExpired:
                logger.warning(f"[{self.router}] Timeout executing '{command}' on attempt {attempt}/{max_retries}.")
            except Exception as e:
                logger.error(f"[{self.router}] Error executing vtysh: {e}")
                
            time.sleep(delay)
            delay *= 2.0
            
        return None

    def collect_bgp_summary(self) -> Dict[str, Any]:
        """Collects BGP peers status (State, PfxRcvd, Uptime)."""
        data = self.exec_vtysh_json("show bgp summary")
        peers_list = []
        
        if data and "ipv4Unicast" in data:
            peers_dict = data["ipv4Unicast"].get("peers", {})
            for peer_ip, details in peers_dict.items():
                peers_list.append({
                    "peer_ip": peer_ip,
                    "remote_as": details.get("remoteAs"),
                    "state": details.get("state"),
                    "uptime": details.get("peerUptime"),
                    "pfx_rcvd": details.get("pfxRcvd", 0),
                    "pfx_sent": details.get("pfxSent", 0)
                })
                
        record = {
            "record_type": "peer_summary",
            "timestamp": time.time(),
            "router": self.router,
            "peers": peers_list
        }
        self.storage.log_event(record)
        return record

    def collect_route_rib(self) -> Dict[str, Any]:
        """Collects IPv4 RIB table with path attributes, AS Paths, and best paths."""
        data = self.exec_vtysh_json("show bgp ipv4 unicast")
        routes_list = []
        
        if data and "routes" in data:
            routes_dict = data["routes"]
            for prefix, paths in routes_dict.items():
                for p in paths:
                    as_path_str = p.get("path", "").strip()
                    path_tokens = as_path_str.split()
                    origin_as = int(path_tokens[-1]) if path_tokens and path_tokens[-1].isdigit() else None
                    nexthops = p.get("nexthops", [{}])
                    nh_ip = nexthops[0].get("ip") if nexthops else None
                    
                    # Extract lastUpdate timestamp from FRR if available
                    last_update_epoch = p.get("lastUpdate", {}).get("epoch", time.time())
                    
                    route_item = {
                        "prefix": prefix,
                        "nexthop": nh_ip,
                        "as_path": as_path_str,
                        "origin_as": origin_as,
                        "as_path_len": len(path_tokens),
                        "loc_pref": p.get("locPrf", 100),
                        "med": p.get("metric", 0),
                        "is_best": p.get("valid", False) and p.get("bestpath", False),
                        "status_code": p.get("status", ""),
                        "last_update_epoch": last_update_epoch
                    }
                    routes_list.append(route_item)
                    
                    # Update Sliding Window Buffer for this prefix
                    self.buffer.append(prefix, {
                        "timestamp": time.time(),
                        "last_update_epoch": last_update_epoch,
                        "as_path": as_path_str,
                        "origin_as": origin_as,
                        "nexthop": nh_ip,
                        "loc_pref": p.get("locPrf", 100),
                        "med": p.get("metric", 0)
                    })
                    
        record = {
            "record_type": "route_rib",
            "timestamp": time.time(),
            "router": self.router,
            "routes": routes_list
        }
        self.storage.log_event(record)
        return record

    def collect_system_metrics(self) -> Dict[str, Any]:
        """Extracts container CPU and Memory telemetry."""
        stats = get_container_stats(self.router)
        record = {
            "record_type": "system_metric",
            "timestamp": time.time(),
            "router": self.router,
            "stats": stats
        }
        self.storage.log_event(record)
        return record

    def poll_once(self):
        """Executes a single comprehensive telemetry extraction iteration."""
        peers = self.collect_bgp_summary()
        routes = self.collect_route_rib()
        sys_metrics = self.collect_system_metrics()
        
        logger.info(
            f"[{self.router}] Telemetry Sampled | Peers: {len(peers.get('peers', []))} | "
            f"Routes: {len(routes.get('routes', []))} | CPU: {sys_metrics['stats']['cpu_perc']} | RAM: {sys_metrics['stats']['mem_usage']}"
        )

    def start_polling(self, duration: Optional[float] = None):
        """Continuously streams telemetry at the given interval."""
        logger.info(f"Starting FRR Telemetry Collector on [{self.router}] every {self.interval}s...")
        self.running = True
        start_time = time.time()
        
        try:
            while self.running:
                self.poll_once()
                if duration and (time.time() - start_time) >= duration:
                    logger.info(f"Completed duration {duration}s polling.")
                    break
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Collector stopped by user.")
        finally:
            self.running = False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FRR Telemetry Collector Daemon")
    parser.add_argument("--router", default="as65003", help="Target FRR container name")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds")
    parser.add_argument("--duration", type=float, default=None, help="Polling duration in seconds (optional)")
    args = parser.parse_args()

    collector = FRRTelemetryCollector(router_container=args.router, poll_interval=args.interval)
    collector.start_polling(duration=args.duration)
