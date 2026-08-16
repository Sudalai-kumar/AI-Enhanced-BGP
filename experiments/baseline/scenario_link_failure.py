"""
Scenario 2: Link Failure & Recovery.
Measures:
1. Route withdrawal / detection latency when transit link (as65001 eth0 / 10.0.12.0/29) goes down.
2. Re-convergence / restoration latency when the link is brought back up.
"""

import time
import os
import sys
from typing import Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from experiments.baseline.benchmark_harness import exec_vtysh_json, exec_cmd, logger

def run_link_failure_iteration() -> Dict[str, float]:
    """Executes a single link failure and restoration benchmark cycle."""
    
    # 1. Ensure network is currently converged
    time.sleep(2.0)
    
    # 2. Inject Link Down on as65001 eth0 (10.0.12.0/29 subnet)
    logger.info("Injecting Link DOWN on as65001 eth0 (net_12: 10.0.12.0/29)...")
    start_down = time.time()
    exec_cmd(["docker", "exec", "as65001", "ip", "link", "set", "eth0", "down"])
    
    withdrawal_latency = 30.0
    # Wait until AS65003 drops the route from RIB
    while time.time() - start_down < 30.0:
        rib = exec_vtysh_json("as65003", "show bgp ipv4 unicast")
        if rib and "routes" in rib:
            if "192.0.2.0/24" not in rib["routes"]:
                withdrawal_latency = time.time() - start_down
                break
        else:
            # RIB empty
            withdrawal_latency = time.time() - start_down
            break
        time.sleep(0.05)
        
    logger.info(f"Route withdrawal observed in {withdrawal_latency:.3f}s")
    
    # Allow hold timer / session state to settle
    time.sleep(2.0)
    
    # 3. Restore Link UP on as65001 eth0
    logger.info("Restoring Link UP on as65001 eth0...")
    start_up = time.time()
    exec_cmd(["docker", "exec", "as65001", "ip", "link", "set", "eth0", "up"])
    
    recovery_latency = 30.0
    while time.time() - start_up < 30.0:
        rib = exec_vtysh_json("as65003", "show bgp ipv4 unicast")
        if rib and "routes" in rib:
            if "192.0.2.0/24" in rib["routes"] and "198.51.100.0/24" in rib["routes"]:
                recovery_latency = time.time() - start_up
                break
        time.sleep(0.05)
        
    logger.info(f"Re-convergence restoration observed in {recovery_latency:.3f}s")
    
    return {
        "withdrawal_latency_sec": round(withdrawal_latency, 3),
        "recovery_latency_sec": round(recovery_latency, 3)
    }
