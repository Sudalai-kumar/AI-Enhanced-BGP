"""
Scenario 1: Cold Start Convergence.
Measures time from full stack start until AS65003 reaches Established state and receives all origin prefixes.
"""

import time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from experiments.baseline.benchmark_harness import exec_vtysh_json, exec_cmd, logger
from scripts.deploy_docker import COMPOSE_FILE

def run_cold_start_iteration() -> float:
    """Executes a single cold start reboot and measures convergence time in seconds."""
    # 1. Restart stack
    exec_cmd(["docker", "compose", "-f", COMPOSE_FILE, "restart"])
    
    start_time = time.time()
    timeout = 30.0
    
    while time.time() - start_time < timeout:
        summary = exec_vtysh_json("as65003", "show bgp summary")
        rib = exec_vtysh_json("as65003", "show bgp ipv4 unicast")
        
        peer_ok = False
        route_ok = False
        
        if summary and "ipv4Unicast" in summary:
            peers = summary["ipv4Unicast"].get("peers", {})
            peer_transit = peers.get("10.0.23.2", {})
            if peer_transit.get("state") == "Established":
                peer_ok = True
                
        if rib and "routes" in rib:
            routes = rib["routes"]
            if "192.0.2.0/24" in routes and "198.51.100.0/24" in routes:
                route_ok = True
                
        if peer_ok and route_ok:
            elapsed = time.time() - start_time
            logger.info(f"Cold start converged in {elapsed:.3f}s")
            return elapsed
            
        time.sleep(0.1)
        
    return timeout
