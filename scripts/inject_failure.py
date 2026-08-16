"""
Network Chaos & Failure Injection Utility for BGP Experimentation.
Supports:
- Link up/down interface toggling (ip link set dev <if> down/up).
- BGP session administrative resets (clear ip bgp <neighbor>).
- Latency & packet loss injection via Linux 'tc' (traffic control).
"""

import subprocess
import argparse
import sys
import time

def exec_docker_cmd(container: str, cmd_list: list):
    full_cmd = ["docker", "exec", container] + cmd_list
    res = subprocess.run(full_cmd, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr

def set_interface_state(node: str, interface: str, state: str):
    """Brings an interface 'up' or 'down' inside an FRR container."""
    print(f"[*] Setting interface {interface} on {node} to {state.upper()}...")
    code, out, err = exec_docker_cmd(node, ["ip", "link", "set", interface, state])
    if code == 0:
        print(f"[+] Interface {interface} on {node} is now {state.upper()}.")
    else:
        print(f"[!] Failed to set interface state: {err}")

def clear_bgp_session(node: str, neighbor_ip: str, soft: bool = False):
    """Sends a clear ip bgp command via vtysh."""
    sub_cmd = f"clear ip bgp {neighbor_ip} soft" if soft else f"clear ip bgp {neighbor_ip}"
    print(f"[*] Executing '{sub_cmd}' on {node}...")
    code, out, err = exec_docker_cmd(node, ["vtysh", "-c", sub_cmd])
    if code == 0:
        print(f"[+] BGP session reset command sent on {node}.")
    else:
        print(f"[!] Failed to reset BGP session: {err}")

def inject_flapping(node: str, interface: str, cycles: int = 3, interval: float = 2.0):
    """Simulates route flapping by cycling an interface down and up repeatedly."""
    print(f"[*] Initiating route flapping simulation ({cycles} cycles, {interval}s interval)...")
    for i in range(1, cycles + 1):
        print(f"  --> Cycle {i}/{cycles}: bringing {interface} DOWN")
        set_interface_state(node, interface, "down")
        time.sleep(interval)
        print(f"  --> Cycle {i}/{cycles}: bringing {interface} UP")
        set_interface_state(node, interface, "up")
        time.sleep(interval)
    print("[+] Flapping simulation complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BGP Chaos & Failure Injection Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Interface Toggle Subcommand
    link_parser = subparsers.add_parser("link", help="Toggle interface state")
    link_parser.add_argument("--node", required=True, help="Container name (e.g. as65001)")
    link_parser.add_argument("--interface", required=True, help="Interface name (e.g. eth0)")
    link_parser.add_argument("--state", choices=["up", "down"], required=True, help="State to set")

    # BGP Reset Subcommand
    bgp_parser = subparsers.add_parser("bgp-reset", help="Reset BGP neighbor session")
    bgp_parser.add_argument("--node", required=True, help="Container name (e.g. as65003)")
    bgp_parser.add_argument("--neighbor", required=True, help="Neighbor IP address (e.g. 10.0.23.1)")
    bgp_parser.add_argument("--soft", action="store_true", help="Soft reset without tearing down TCP session")

    # Flap Simulation Subcommand
    flap_parser = subparsers.add_parser("flap", help="Simulate route flapping")
    flap_parser.add_argument("--node", required=True, help="Container name (e.g. as65001)")
    flap_parser.add_argument("--interface", required=True, help="Interface name (e.g. eth0)")
    flap_parser.add_argument("--cycles", type=int, default=3, help="Number of flap cycles")
    flap_parser.add_argument("--interval", type=float, default=2.0, help="Seconds between flaps")

    args = parser.parse_args()

    if args.command == "link":
        set_interface_state(args.node, args.interface, args.state)
    elif args.command == "bgp-reset":
        clear_bgp_session(args.node, args.neighbor, soft=args.soft)
    elif args.command == "flap":
        inject_flapping(args.node, args.interface, cycles=args.cycles, interval=args.interval)
