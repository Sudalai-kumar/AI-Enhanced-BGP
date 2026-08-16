"""
Automated Docker Compose Orchestration & Lifecycle Manager.
Supports clean setup, teardown, and status reporting on Windows / Linux.
"""

import subprocess
import sys
import os
import time
import argparse

COMPOSE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "topologies", "docker-compose.yml"))

def run_cmd(cmd_list):
    res = subprocess.run(cmd_list, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr

def up():
    print(f"[*] Deploying multi-AS BGP topology from: {COMPOSE_FILE}")
    code, out, err = run_cmd(["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"])
    if code == 0:
        print("[+] All FRR containers started successfully.")
        print(out)
    else:
        print(f"[!] Deployment failed:\n{err}")
        sys.exit(code)

def down():
    print(f"[*] Tearing down multi-AS BGP topology...")
    code, out, err = run_cmd(["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"])
    if code == 0:
        print("[+] All FRR containers and networks stopped and cleaned up.")
    else:
        print(f"[!] Teardown failed:\n{err}")

def status():
    print("[*] Checking BGP container status...")
    code, out, err = run_cmd(["docker", "compose", "-f", COMPOSE_FILE, "ps"])
    print(out if code == 0 else err)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-AS Docker Manager")
    parser.add_argument("action", choices=["up", "down", "restart", "status"], help="Action to execute")
    args = parser.parse_args()

    if args.action == "up":
        up()
    elif args.action == "down":
        down()
    elif args.action == "restart":
        down()
        time.sleep(2)
        up()
    elif args.action == "status":
        status()
