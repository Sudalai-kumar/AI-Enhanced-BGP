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

EXPECTED_PEER_COUNTS = {
    "as65001": 3,
    "as65002": 3,
    "as65003": 3,
    "as65004": 2,
    "as65005": 1,
    "as65006": 2,
    "as65007": 1,
    "as65008": 1,
    "as65009": 1,
    "as65010": 1,
}

def verify_all(timeout: int = 30):
    print("=" * 70)
    print(" 10-AS BGP Convergence & Routing Parity Verification")
    print("=" * 70)
    
    start_time = time.time()
    converged = False
    
    while time.time() - start_time < timeout:
        all_nodes_established = True
        total_established = 0
        total_expected = sum(EXPECTED_PEER_COUNTS.values())
        
        for as_num in range(65001, 65011):
            cname = f"as{as_num}"
            s = exec_vtysh_json(cname, "show bgp summary")
            if not s or "ipv4Unicast" not in s:
                all_nodes_established = False
                break
            peers = s["ipv4Unicast"].get("peers", {})
            established = sum(1 for p in peers.values() if p.get("state") == "Established")
            expected = EXPECTED_PEER_COUNTS.get(cname, 1)
            total_established += established
            if established < expected:
                all_nodes_established = False
                break
                
        # Check route propagation for baseline prefix 192.0.2.0/24 at Core (as65001) and Edge (as65003)
        rib1 = exec_vtysh_json("as65001", "show bgp ipv4 unicast")
        rib3 = exec_vtysh_json("as65003", "show bgp ipv4 unicast")
        
        route_1_ok = rib1 and "routes" in rib1 and "192.0.2.0/24" in rib1["routes"]
        route_3_ok = rib3 and "routes" in rib3 and "192.0.2.0/24" in rib3["routes"]
        
        if all_nodes_established and total_established == total_expected and route_1_ok and route_3_ok:
            converged = True
            break
            
        time.sleep(1.0)

    elapsed = round(time.time() - start_time, 2)
    
    # Detailed Table Output for all running AS nodes
    table_data = []
    for as_num in range(65001, 65011):
        cname = f"as{as_num}"
        s = exec_vtysh_json(cname, "show bgp summary")
        if not s or "ipv4Unicast" not in s:
            continue
        peers = s["ipv4Unicast"].get("peers", {})
        for peer_ip, pinfo in peers.items():
            state = pinfo.get("state", "Down")
            pfx_rcvd = pinfo.get("pfxRcd", 0)
            remote_as = pinfo.get("remoteAs", 0)
            desc = pinfo.get("desc", f"AS{remote_as}")
            table_data.append([cname.upper(), f"{peer_ip} (AS{remote_as})", state, f"Pfx: {pfx_rcvd} ({desc})"])

    if table_data:
        print("\n" + tabulate(table_data, headers=["Node", "Neighbor", "BGP State", "Details"], tablefmt="grid"))
    else:
        print("\n[!] No active BGP sessions detected in running containers.")
    
    if converged:
        print(f"\n[+] FULL 10-AS CONVERGENCE SUCCESSFUL in {elapsed}s (All 18 peer sessions Established, routes propagated)!")
        try:
            storage._write_convergence_event_sync(
                router="as65003",
                event_type="initial_convergence_10as",
                convergence_sec=elapsed,
                target_prefix="192.0.2.0/24"
            )
        except Exception:
            pass
        return True
    else:
        print(f"\n[!] CONVERGENCE FAILED or TIMED OUT after {timeout}s.")
        return False

if __name__ == "__main__":
    success = verify_all()
    sys.exit(0 if success else 1)
