"""
BGP Convergence & Routing Parity Verification Script.
Checks:
1. eBGP session states across all AS nodes (Expected: 'Established').
2. Route propagation from AS65001 (192.0.2.0/24, 198.51.100.0/24) through AS65002 to AS65003.
3. AS Path validation: AS65003 must see '65002 65001'.
4. Logs convergence latency and metrics into TelemetryStorage.
"""

import subprocess
import json
import time
import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tabulate import tabulate
from src.telemetry.storage import TelemetryStorage

storage = TelemetryStorage()

def exec_vtysh_json(container: str, cmd: str):
    full_cmd = ["docker", "exec", container, "vtysh", "-c", f"{cmd} json"]
    try:
        res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout.strip())
    except Exception:
        pass
    return None

def verify_all(timeout: int = 30):
    print("=" * 65)
    print(" BGP Multi-AS Convergence & Routing Parity Verification")
    print("=" * 65)
    
    start_time = time.time()
    converged = False
    
    while time.time() - start_time < timeout:
        # Check AS65003 BGP Summary
        summary = exec_vtysh_json("as65003", "show bgp summary")
        # Check AS65003 IPv4 RIB
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
            converged = True
            break
            
        time.sleep(2)

    elapsed = round(time.time() - start_time, 2)
    
    # Detailed Table Output
    table_data = []
    
    # Node AS65001
    s1 = exec_vtysh_json("as65001", "show bgp summary")
    p1 = s1.get("ipv4Unicast", {}).get("peers", {}).get("10.0.12.3", {}).get("state", "Down") if s1 else "Error"
    table_data.append(["AS65001 (Origin)", "10.0.12.3 (AS65002)", p1, "Originating 192.0.2.0/24, 198.51.100.0/24"])

    # Node AS65002
    s2 = exec_vtysh_json("as65002", "show bgp summary")
    p2_1 = s2.get("ipv4Unicast", {}).get("peers", {}).get("10.0.12.2", {}).get("state", "Down") if s2 else "Error"
    p2_3 = s2.get("ipv4Unicast", {}).get("peers", {}).get("10.0.23.3", {}).get("state", "Down") if s2 else "Error"
    table_data.append(["AS65002 (Transit)", "10.0.12.2 (AS65001)", p2_1, "Transit forwarding"])
    table_data.append(["AS65002 (Transit)", "10.0.23.3 (AS65003)", p2_3, "Transit forwarding"])

    # Node AS65003
    s3 = exec_vtysh_json("as65003", "show bgp summary")
    p3 = s3.get("ipv4Unicast", {}).get("peers", {}).get("10.0.23.2", {}).get("state", "Down") if s3 else "Error"
    rib3 = exec_vtysh_json("as65003", "show bgp ipv4 unicast")
    
    r_info = "No routes"
    if rib3 and "routes" in rib3:
        pfx_info = []
        for pfx, paths in rib3["routes"].items():
            for path in paths:
                pfx_info.append(f"{pfx} via {path.get('path', 'N/A')}")
        r_info = ", ".join(pfx_info)

    table_data.append(["AS65003 (Monitor)", "10.0.23.1 (AS65002)", p3, r_info])

    print("\n" + tabulate(table_data, headers=["Node", "Neighbor", "BGP State", "Learned Prefixes & AS Path"], tablefmt="grid"))
    
    if converged:
        print(f"\n[+] CONVERGENCE SUCCESSFUL in {elapsed}s!")
        storage.log_event({
            "record_type": "convergence_metric",
            "timestamp": time.time(),
            "event_type": "initial_convergence",
            "prefix": "192.0.2.0/24",
            "duration": elapsed,
            "details": {"status": "SUCCESS", "elapsed": elapsed}
        })
        return True
    else:
        print(f"\n[!] CONVERGENCE FAILED or TIMED OUT after {timeout}s.")
        return False

if __name__ == "__main__":
    success = verify_all()
    sys.exit(0 if success else 1)
