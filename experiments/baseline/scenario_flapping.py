"""
Scenario 3: Route Flapping & Oscillation Benchmark.
Quantifies BGP UPDATE count, route oscillation frequency, and stabilization time during repetitive link flaps.
"""

import time
import os
import sys
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from experiments.baseline.benchmark_harness import exec_vtysh_json, exec_cmd, logger

def get_neighbor_msg_stats(router: str, neighbor_ip: str) -> Dict[str, int]:
    """Extracts BGP message stats (msgRcvd, msgSent, tableVersion)."""
    data = exec_vtysh_json(router, "show bgp summary")
    if data and "ipv4Unicast" in data:
        peers = data["ipv4Unicast"].get("peers", {})
        if neighbor_ip in peers:
            p_data = peers[neighbor_ip]
            return {
                "msg_rcvd": p_data.get("msgRcvd", 0),
                "msg_sent": p_data.get("msgSent", 0),
                "table_version": data["ipv4Unicast"].get("tableVersion", 0)
            }
    return {"msg_rcvd": 0, "msg_sent": 0, "table_version": 0}

def run_flapping_iteration(cycles: int = 3, interval: float = 1.5) -> Dict[str, Any]:
    """Executes a series of link flaps on as65001 eth0 and records churn."""
    logger.info(f"Starting flapping benchmark: {cycles} cycles at {interval}s interval...")
    
    # Get initial message counts and table version at AS65003
    init_stats = get_neighbor_msg_stats("as65003", "10.0.23.2")
    
    start_time = time.time()
    for i in range(1, cycles + 1):
        exec_cmd(["docker", "exec", "as65001", "ip", "link", "set", "eth0", "down"])
        time.sleep(interval)
        exec_cmd(["docker", "exec", "as65001", "ip", "link", "set", "eth0", "up"])
        time.sleep(interval)
        
    # Wait for convergence stabilization
    time.sleep(2.0)
    final_stats = get_neighbor_msg_stats("as65003", "10.0.23.2")
    
    messages_generated = max(0, final_stats["msg_rcvd"] - init_stats["msg_rcvd"])
    table_changes = max(0, final_stats["table_version"] - init_stats["table_version"])
    elapsed = time.time() - start_time
    
    return {
        "flap_cycles": cycles,
        "duration_sec": round(elapsed, 2),
        "bgp_updates_received_as65003": messages_generated,
        "rib_table_version_increments": table_changes,
        "oscillation_rate_per_min": round((cycles / (elapsed / 60.0)), 2)
    }
