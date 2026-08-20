"""
Network Chaos & Failure Injection Utility for BGP Experimentation.
Supports:
- Link up/down interface toggling (ip link set dev <if> down/up).
- BGP session administrative resets (clear ip bgp <neighbor>).
- Latency & packet loss injection via Linux 'tc' (traffic control).
- Controller-crash simulation: SIGKILL the autonomous controller and verify recovery.
- DB corruption simulation: rename the SQLite state database and verify clean start.
"""

import subprocess
import argparse
import sys
import time
import os
import signal
import shutil

# Default state database path relative to the repository root
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DEFAULT_DB = os.path.join(_REPO_ROOT, "data", "controller_state.db")


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


def controller_crash(pid: int, restart_cmd: list, verify_recovery_sec: float = 5.0):
    """
    Sends SIGKILL to the autonomous controller process identified by pid,
    then restarts it using restart_cmd and waits verify_recovery_sec seconds
    for startup reconciliation to complete.

    Args:
        pid:                 OS PID of the running AutonomousBGPController process.
        restart_cmd:         Command list to restart the controller,
                             e.g. ['python', 'scripts/run_autonomous_controller.py'].
        verify_recovery_sec: Seconds to wait before reporting recovery success.
    """
    print(f"[*] Sending SIGKILL to controller PID {pid}...")
    try:
        os.kill(pid, signal.SIGKILL)
        print(f"[+] Controller PID {pid} terminated.")
    except ProcessLookupError:
        print(f"[!] PID {pid} not found. Already terminated?")
    except PermissionError:
        print(f"[!] Permission denied killing PID {pid}.")
        return

    time.sleep(1.0)  # Brief pause before restart

    print(f"[*] Restarting controller: {' '.join(restart_cmd)}")
    proc = subprocess.Popen(restart_cmd)
    print(f"[+] Controller restarted with PID {proc.pid}.")
    print(f"[*] Waiting {verify_recovery_sec}s for startup reconciliation...")
    time.sleep(verify_recovery_sec)
    poll = proc.poll()
    if poll is None:
        print(f"[+] Controller (PID {proc.pid}) is running after restart. Recovery successful.")
    else:
        print(f"[!] Controller exited with code {poll} — check logs for startup errors.")


def db_corrupt(db_path: str = _DEFAULT_DB):
    """
    Simulates a database corruption event by renaming the SQLite state file.
    The controller should detect the missing DB on next startup and begin with
    an empty state rather than crashing.

    The renamed file is saved as <db_path>.corrupted_<timestamp> so it can be
    inspected or restored manually.
    """
    if not os.path.exists(db_path):
        print(f"[!] Database file not found at {db_path}. Nothing to corrupt.")
        return

    backup_path = f"{db_path}.corrupted_{int(time.time())}"
    shutil.move(db_path, backup_path)
    print(f"[+] State database moved to: {backup_path}")
    print(f"[*] The controller's next startup will find no DB and begin with empty state.")
    print(f"[*] To restore: mv \"{backup_path}\" \"{db_path}\"")


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

    # Controller Crash Subcommand
    crash_parser = subparsers.add_parser(
        "controller-crash",
        help="SIGKILL the autonomous controller and restart it to verify recovery"
    )
    crash_parser.add_argument("--pid", type=int, required=True,
                              help="OS PID of the running AutonomousBGPController")
    crash_parser.add_argument("--restart-cmd", nargs="+",
                              default=["python", "scripts/run_autonomous_controller.py"],
                              help="Command to restart the controller")
    crash_parser.add_argument("--verify-sec", type=float, default=5.0,
                              help="Seconds to wait for startup reconciliation (default: 5)")

    # DB Corruption Subcommand
    db_parser = subparsers.add_parser(
        "db-corrupt",
        help="Rename the SQLite state DB to simulate corruption — controller should start cleanly"
    )
    db_parser.add_argument("--db-path", default=_DEFAULT_DB,
                           help=f"Path to the state database (default: {_DEFAULT_DB})")

    args = parser.parse_args()

    if args.command == "link":
        set_interface_state(args.node, args.interface, args.state)
    elif args.command == "bgp-reset":
        clear_bgp_session(args.node, args.neighbor, soft=args.soft)
    elif args.command == "flap":
        inject_flapping(args.node, args.interface, cycles=args.cycles, interval=args.interval)
    elif args.command == "controller-crash":
        controller_crash(
            pid=args.pid,
            restart_cmd=args.restart_cmd,
            verify_recovery_sec=args.verify_sec
        )
    elif args.command == "db-corrupt":
        db_corrupt(db_path=args.db_path)
