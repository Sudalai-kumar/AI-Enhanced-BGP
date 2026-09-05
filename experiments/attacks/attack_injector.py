"""
Programmable BGP Attack Injector (Async-enabled).
"""

import time
import os
import sys
import asyncio
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.utils.logger import setup_logger
from src.utils.async_utils import run_subprocess_async
from experiments.attacks.historical_signatures import HISTORICAL_INCIDENTS

logger = setup_logger("attack_injector")

class BGPAttackInjector:
    def __init__(self, rogue_container: str = "as65010", origin_container: str = "as65007"):
        self.rogue = rogue_container
        self.origin = origin_container

    @staticmethod
    def _get_as_num(container: str, default: int = 65010) -> int:
        digits = "".join(c for c in container if c.isdigit())
        return int(digits) if digits else default

    async def exec_vtysh(self, container: str, commands: list) -> tuple:
        input_bytes = ("\n".join(commands) + "\n").encode()
        try:
            rc, stdout, stderr = await run_subprocess_async(
                "docker", "exec", "-i", container, "vtysh",
                stdin_data=input_bytes,
                timeout=6.0
            )
            return rc, stdout.decode(errors="replace"), stderr.decode(errors="replace")
        except asyncio.TimeoutError:
            logger.error(f"[{container}] vtysh command timed out during attack injection")
            return 1, "", "TimeoutError"
        except Exception as e:
            logger.error(f"[{container}] Error executing vtysh: {e}")
            return 1, "", str(e)

    async def inject_direct_hijack(self, prefix: str = "192.0.2.0/24", rogue_origin_as: Optional[int] = None) -> bool:
        """Injects a rogue direct prefix announcement from the rogue router."""
        as_num = rogue_origin_as or self._get_as_num(self.rogue, 65010)
        logger.info(f"Injecting Direct Prefix Hijack on {self.rogue} for {prefix} (Origin AS: {as_num})...")
        cmds = [
            "configure terminal",
            f"ip route {prefix} Null0",
            f"router bgp {as_num}",
            " address-family ipv4 unicast",
            f"  network {prefix}",
            " exit-address-family",
            "exit",
            "exit",
            "clear ip bgp * soft out"
        ]
        code, out, err = await self.exec_vtysh(self.rogue, cmds)
        return code == 0

    async def inject_subprefix_hijack(self, subprefix: str = "192.0.2.0/25", rogue_origin_as: Optional[int] = None) -> bool:
        """Injects a more specific sub-prefix announcement."""
        as_num = rogue_origin_as or self._get_as_num(self.rogue, 65010)
        logger.info(f"Injecting Sub-Prefix Hijack on {self.rogue} for {subprefix} (Origin AS: {as_num})...")
        cmds = [
            "configure terminal",
            f"ip route {subprefix} Null0",
            f"router bgp {as_num}",
            " address-family ipv4 unicast",
            f"  network {subprefix}",
            " exit-address-family",
            "exit",
            "exit",
            "clear ip bgp * soft out"
        ]
        code, out, err = await self.exec_vtysh(self.rogue, cmds)
        return code == 0

    async def inject_route_leak(self, prefix: str = "192.0.2.0/24", leaked_as_path: str = "65002 65004 65004 65001") -> bool:
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
        code, out, err = await self.exec_vtysh(self.origin, cmds)
        return code == 0

    async def inject_burst_flapping(self, prefix: str = "192.0.2.0/24", cycles: int = 4, interval: float = 0.4):
        """Simulates rapid advertisement burst flooding."""
        as_num = self._get_as_num(self.origin, 65007)
        logger.info(f"Injecting Burst Flapping on {self.origin} (AS{as_num}): {cycles} cycles at {interval}s interval...")
        for i in range(1, cycles + 1):
            await self.exec_vtysh(self.origin, [
                "configure terminal",
                f"router bgp {as_num}",
                " address-family ipv4 unicast",
                f"  no network {prefix}",
                " exit-address-family",
                "exit",
                "exit",
                "clear ip bgp * soft out"
            ])
            await asyncio.sleep(interval)
            await self.exec_vtysh(self.origin, [
                "configure terminal",
                f"router bgp {as_num}",
                " address-family ipv4 unicast",
                f"  network {prefix}",
                " exit-address-family",
                "exit",
                "exit",
                "clear ip bgp * soft out"
            ])
            await asyncio.sleep(interval)

    async def inject_historical_replay(self, incident_key: str) -> bool:
        """Replays mapped historical anomaly signature onto the multi-AS testbed."""
        incident = HISTORICAL_INCIDENTS.get(incident_key)
        if not incident:
            logger.error(f"Incident key '{incident_key}' not found.")
            return False
            
        pfx = incident["target_prefix"]
        as_num = self._get_as_num(self.rogue, 65010)
        logger.info(f"Replaying signature for '{incident['name']}' (Prefix: {pfx}) on {self.rogue} (AS{as_num})...")
        
        cmds = [
            "configure terminal",
            f"ip route {pfx} Null0",
            f"router bgp {as_num}",
            " address-family ipv4 unicast",
            f"  network {pfx}",
            " exit-address-family",
            "exit",
            "exit",
            "clear ip bgp * soft out"
        ]
        code, out, err = await self.exec_vtysh(self.rogue, cmds)
        return code == 0

    async def cleanup_all_attacks(self):
        """Restores rogue, origin, and secondary routers to clean baseline configurations."""
        rogue_as = self._get_as_num(self.rogue, 65010)
        origin_as = self._get_as_num(self.origin, 65007)

        # Clean rogue router
        await self.exec_vtysh(self.rogue, [
            "configure terminal",
            f"router bgp {rogue_as}",
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

        # Clean origin router
        await self.exec_vtysh(self.origin, [
            "configure terminal",
            "route-map RM_OUT permit 10",
            " no set as-path prepend",
            "exit",
            f"router bgp {origin_as}",
            " address-family ipv4 unicast",
            "  network 192.0.2.0/24",
            " exit-address-family",
            "exit",
            "exit",
            "clear ip bgp * soft out"
        ])

        # Also clean legacy as65004 / as65001 if different
        if self.rogue != "as65004":
            try:
                await self.exec_vtysh("as65004", [
                    "configure terminal",
                    "router bgp 65004",
                    " address-family ipv4 unicast",
                    "  no network 192.0.2.0/24",
                    "  no network 192.0.2.0/25",
                    "  no network 208.65.153.0/24",
                    " exit-address-family",
                    "exit",
                    "exit",
                    "clear ip bgp * soft out"
                ])
            except Exception:
                pass

        if self.origin != "as65001":
            try:
                await self.exec_vtysh("as65001", [
                    "configure terminal",
                    "route-map RM_OUT permit 10",
                    " no set as-path prepend",
                    "exit",
                    "clear ip bgp * soft out"
                ])
            except Exception:
                pass

        await asyncio.sleep(0.5)
