"""
Fixed Programmable BGP Attack Injector using real leaked_as_path parameter.
"""

import subprocess
import time
import os
import sys
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.utils.logger import setup_logger
from experiments.attacks.historical_signatures import HISTORICAL_INCIDENTS

logger = setup_logger("attack_injector")

class BGPAttackInjector:
    def __init__(self, rogue_container: str = "as65004", origin_container: str = "as65001"):
        self.rogue = rogue_container
        self.origin = origin_container

    def exec_vtysh(self, container: str, commands: list) -> tuple:
        full_cmd = ["docker", "exec", "-i", container, "vtysh"]
        input_str = "\n".join(commands) + "\n"
        res = subprocess.run(full_cmd, input=input_str, capture_output=True, text=True)
        return res.returncode, res.stdout, res.stderr

    def inject_direct_hijack(self, prefix: str = "192.0.2.0/24", rogue_origin_as: int = 65004) -> bool:
        """Injects a rogue direct prefix announcement from as65004."""
        logger.info(f"Injecting Direct Prefix Hijack on {self.rogue} for {prefix} (Origin AS: {rogue_origin_as})...")
        cmds = [
            "configure terminal",
            f"ip route {prefix} Null0",
            f"router bgp {rogue_origin_as}",
            " address-family ipv4 unicast",
            f"  network {prefix}",
            " exit-address-family",
            "exit",
            "exit",
            "clear ip bgp * soft out"
        ]
        code, out, err = self.exec_vtysh(self.rogue, cmds)
        return code == 0

    def inject_subprefix_hijack(self, subprefix: str = "192.0.2.0/25", rogue_origin_as: int = 65004) -> bool:
        """Injects a more specific sub-prefix announcement."""
        logger.info(f"Injecting Sub-Prefix Hijack on {self.rogue} for {subprefix} (Origin AS: {rogue_origin_as})...")
        cmds = [
            "configure terminal",
            f"ip route {subprefix} Null0",
            f"router bgp {rogue_origin_as}",
            " address-family ipv4 unicast",
            f"  network {subprefix}",
            " exit-address-family",
            "exit",
            "exit",
            "clear ip bgp * soft out"
        ]
        code, out, err = self.exec_vtysh(self.rogue, cmds)
        return code == 0

    def inject_route_leak(self, prefix: str = "192.0.2.0/24", leaked_as_path: str = "65002 65004 65004 65001") -> bool:
        """Injects a multi-hop transit route leak utilizing the actual leaked_as_path argument."""
        logger.info(f"Injecting Route Leak on {self.origin} with path '{leaked_as_path}'...")
        cmds = [
            "configure terminal",
            "route-map RM_OUT permit 10",
            f" set as-path prepend {leaked_as_path}",
            "exit",
            "exit",
            "clear ip bgp * soft out"
        ]
        code, out, err = self.exec_vtysh(self.origin, cmds)
        return code == 0

    def inject_burst_flapping(self, prefix: str = "192.0.2.0/24", cycles: int = 4, interval: float = 0.4):
        """Simulates rapid advertisement burst flooding."""
        logger.info(f"Injecting Burst Flapping: {cycles} cycles at {interval}s interval...")
        for i in range(1, cycles + 1):
            self.exec_vtysh(self.origin, [
                "configure terminal",
                "router bgp 65001",
                " address-family ipv4 unicast",
                f"  no network {prefix}",
                " exit-address-family",
                "exit",
                "exit",
                "clear ip bgp * soft out"
            ])
            time.sleep(interval)
            self.exec_vtysh(self.origin, [
                "configure terminal",
                "router bgp 65001",
                " address-family ipv4 unicast",
                f"  network {prefix}",
                " exit-address-family",
                "exit",
                "exit",
                "clear ip bgp * soft out"
            ])
            time.sleep(interval)

    def inject_historical_replay(self, incident_key: str) -> bool:
        """Replays mapped historical anomaly signature onto the multi-AS testbed."""
        incident = HISTORICAL_INCIDENTS.get(incident_key)
        if not incident:
            logger.error(f"Incident key '{incident_key}' not found.")
            return False
            
        pfx = incident["target_prefix"]
        logger.info(f"Replaying signature for '{incident['name']}' (Prefix: {pfx})...")
        
        cmds = [
            "configure terminal",
            f"ip route {pfx} Null0",
            f"router bgp 65004",
            " address-family ipv4 unicast",
            f"  network {pfx}",
            " exit-address-family",
            "exit",
            "exit",
            "clear ip bgp * soft out"
        ]
        code, out, err = self.exec_vtysh(self.rogue, cmds)
        return code == 0

    def cleanup_all_attacks(self):
        """Restores both as65004 and as65001 to clean baseline configurations."""
        self.exec_vtysh(self.rogue, [
            "configure terminal",
            "router bgp 65004",
            " address-family ipv4 unicast",
            "  no network 192.0.2.0/24",
            "  no network 192.0.2.0/25",
            "  no network 208.65.153.0/24",
            "  no network 8.8.8.0/24",
            "  no network 104.16.0.0/16",
            " exit-address-family",
            "exit",
            "exit",
            "clear ip bgp * soft out"
        ])
        self.exec_vtysh(self.origin, [
            "configure terminal",
            "route-map RM_OUT permit 10",
            " no set as-path prepend",
            "exit",
            "router bgp 65001",
            " address-family ipv4 unicast",
            "  network 192.0.2.0/24",
            "  network 198.51.100.0/24",
            " exit-address-family",
            "exit",
            "exit",
            "clear ip bgp * soft out"
        ])
        time.sleep(0.5)
