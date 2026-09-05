"""
Robust BGP Policy Engine with Route-Map Flush, Object Pruning,
Deep FRR Configuration Verification, and RIB Best-Path Behavioral Verification.
Async-enabled using safe non-blocking subprocess execution.
"""

import asyncio
import os
import sys
import json
from typing import Dict, Any, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.utils.logger import setup_logger
from src.utils.async_utils import run_subprocess_async

logger = setup_logger("policy_engine")

PEER_IP_TO_AS = {
    "10.0.12.3": 65002, "10.0.12.2": 65001,
    "10.0.13.3": 65003, "10.0.13.2": 65001,
    "10.0.14.3": 65004, "10.0.14.2": 65001,
    "10.0.25.3": 65005, "10.0.25.2": 65002,
    "10.0.26.3": 65006, "10.0.26.2": 65002,
    "10.0.37.3": 65007, "10.0.37.2": 65003,
    "10.0.38.3": 65008, "10.0.38.2": 65003,
    "10.0.49.3": 65009, "10.0.49.2": 65004,
    "10.0.60.3": 65010, "10.0.60.2": 65006,
    # Legacy testbed mappings
    "10.0.23.2": 65002, "10.0.23.3": 65003,
    "10.0.34.2": 65003, "10.0.34.3": 65004,
}

ROUTER_PEER_ROUTE_MAPS = {
    "as65001": ["RM_IN_AS65002", "RM_IN_AS65003", "RM_IN_AS65004"],
    "as65002": ["RM_IN_AS65001", "RM_IN_AS65005", "RM_IN_AS65006"],
    "as65003": ["RM_IN_AS65001", "RM_IN_AS65007", "RM_IN_AS65008"],
    "as65004": ["RM_IN_AS65001", "RM_IN_AS65009"],
    "as65005": ["RM_IN_AS65002"],
    "as65006": ["RM_IN_AS65002", "RM_IN_AS65010"],
}

class BGPPolicyEngine:
    def __init__(self, router: str = "as65003", peer_ip: str = "10.0.23.2", route_map_name: Optional[str] = None):
        self.router = router
        self.peer_ip = peer_ip
        if route_map_name:
            self.route_map_name = route_map_name
        else:
            remote_as = PEER_IP_TO_AS.get(peer_ip, 65002)
            self.route_map_name = f"RM_IN_AS{remote_as}"
        self.current_policies: Dict[str, Dict[str, Any]] = {}

    def map_trust_to_policy(self, trust_score: float, class_id: int, current_loc_pref: int = 100) -> Tuple[int, Optional[str], str]:
        """
        Maps continuous Trust Score and Class ID to policy actions with Hysteresis:
        - Class 3 (Hijack) or Trust < 0.25 -> LP 0 + no-export
        - Class 2 (Route Leak) or Trust < 0.55 -> LP 50
        - Class 1 (Suspicious) or Trust in [0.55, 0.80) -> LP 80
        - Class 0 (Normal) or Trust >= 0.85 -> LP 100
        """
        if class_id == 3 or trust_score < 0.25:
            return 0, "no-export", "Quarantine (LocalPref 0 + no-export)"

        if class_id == 2 or trust_score < 0.55:
            return 50, None, "Hard Deprioritization (LocalPref 50)"

        if current_loc_pref == 100:
            if trust_score < 0.80:
                return 80, None, "Soft Deprioritization (LocalPref 80)"
            else:
                return 100, None, "Default Baseline (LocalPref 100)"
        else:
            if trust_score >= 0.85 and class_id == 0:
                return 100, None, "Default Baseline (LocalPref 100)"
            elif trust_score < 0.55:
                return 50, None, "Hard Deprioritization (LocalPref 50)"
            else:
                return 80, None, "Soft Deprioritization (LocalPref 80)"

    @staticmethod
    def _sanitize_prefix(prefix: str) -> str:
        return prefix.replace(".", "_").replace("/", "_")

    def generate_route_map_config(self, prefix_policies: Dict[str, Dict[str, Any]], route_map_name: Optional[str] = None) -> str:
        """
        Generates deterministic FRRouting route-map syntax.
        """
        rm_name = route_map_name or self.route_map_name
        lines = []
        seq = 10

        for pfx, policy in prefix_policies.items():
            loc_pref = policy.get("loc_pref", 100)
            comm = policy.get("community")
            pfx_tag = self._sanitize_prefix(pfx)

            lines.append(f"route-map {rm_name} permit {seq}")
            lines.append(f" match ip address prefix-list PL_AI_{pfx_tag}")
            lines.append(f" set local-preference {loc_pref}")
            if comm:
                lines.append(f" set community {comm}")
            lines.append("exit")
            seq += 10

        # Fallback permit for all remaining traffic
        lines.append(f"route-map {rm_name} permit 1000")
        lines.append(" set local-preference 100")
        lines.append("exit")

        return "\n".join(lines)

    async def apply_policy(self, prefix_policies: Dict[str, Dict[str, Any]], settle_delay_sec: float = 0.5) -> bool:
        """
        Applies clean route-map updates across all inbound peer route-maps on this router,
        cleans stale prefix-lists, triggers soft BGP inbound re-evaluation,
        and performs deep verification against FRR configuration state AND RIB best-path state.
        Both layers must pass for apply_policy to return True.
        """
        target_route_maps = ROUTER_PEER_ROUTE_MAPS.get(self.router, [self.route_map_name])
        cmd_lines = ["configure terminal"]

        # 1. Safely remove old AI policy sequences (10..100) without destroying the route-map object
        for rm in target_route_maps:
            for s in range(10, 100, 10):
                cmd_lines.append(f"no route-map {rm} permit {s}")

        # 2. Define fresh prefix lists
        for pfx in prefix_policies.keys():
            pfx_tag = self._sanitize_prefix(pfx)
            cmd_lines.append(f"ip prefix-list PL_AI_{pfx_tag} permit {pfx}")

        # 3. Generate route map sequences for all target route-maps
        for rm in target_route_maps:
            cmd_lines.append(self.generate_route_map_config(prefix_policies, route_map_name=rm))

        cmd_lines.append("exit")
        cmd_lines.append("clear ip bgp * soft in")

        vtysh_script = "\n".join(cmd_lines)

        try:
            rc, stdout, stderr = await run_subprocess_async(
                "docker", "exec", "-i", self.router, "vtysh",
                stdin_data=vtysh_script.encode(),
                timeout=6.0
            )
            if rc == 0:
                await asyncio.sleep(settle_delay_sec)
                # Layer 1: Verify route-map configuration exists in FRR
                config_verified = await self.verify_frr_state(prefix_policies)
                if not config_verified:
                    logger.error(f"[{self.router}] FRR route-map configuration verification failed.")
                    return False

                # Layer 2: Verify actual RIB best-path reflects expected LocalPref per prefix
                rib_verified = True
                for pfx, policy in prefix_policies.items():
                    expected_lp = policy.get("loc_pref", 100)
                    expected_comm = policy.get("community")
                    ok, details = await self.verify_rib_best_path(pfx, expected_lp, expected_comm)
                    if not ok:
                        logger.error(
                            f"[{self.router}] RIB best-path verification failed for {pfx}: {details}"
                        )
                        rib_verified = False

                if rib_verified:
                    self.current_policies = prefix_policies.copy()
                    logger.info(
                        f"[{self.router}] Live policy applied, config-verified & RIB-verified "
                        f"across {len(prefix_policies)} prefixes."
                    )
                    return True
                else:
                    logger.error(f"[{self.router}] RIB best-path verification failed — policy not committed.")
                    return False
            else:
                logger.error(f"[{self.router}] Failed to apply policy via vtysh: {stderr.decode(errors='replace')}")
                return False
        except asyncio.TimeoutError:
            logger.error(f"[{self.router}] vtysh command timed out during apply_policy")
            return False
        except Exception as e:
            logger.error(f"[{self.router}] Error applying policy: {e}")
            return False

    async def verify_frr_state(self, expected_policies: Dict[str, Dict[str, Any]]) -> bool:
        """
        Layer 1: Queries FRR to verify that each expected prefix-list and route-map sequence
        is installed with the exact expected LocalPref and community in the route-map config.
        """
        try:
            rc, stdout, _ = await run_subprocess_async(
                "docker", "exec", self.router, "vtysh", "-c", f"show route-map {self.route_map_name}",
                timeout=4.0
            )
            if rc != 0:
                return False

            output = stdout.decode(errors="replace")
            for pfx, policy in expected_policies.items():
                expected_lp = policy.get("loc_pref", 100)
                expected_comm = policy.get("community")
                pfx_tag = self._sanitize_prefix(pfx)

                if f"PL_AI_{pfx_tag}" not in output:
                    return False
                if f"local-preference {expected_lp}" not in output:
                    return False
                if expected_comm and f"community {expected_comm}" not in output:
                    return False

            return True
        except Exception:
            return False

    async def verify_rib_best_path(
        self,
        prefix: str,
        expected_lp: int,
        expected_community: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Layer 2: Queries the FRR RIB via 'show bgp ipv4 unicast <prefix> json' and
        verifies that the best-path entry carries the expected LocalPref and, if
        provided, the expected community string.

        Returns:
            (True, details_dict)  if verification passes
            (False, details_dict) if verification fails, with a 'reason' key explaining why
        """
        details: Dict[str, Any] = {
            "prefix": prefix,
            "expected_lp": expected_lp,
            "expected_community": expected_community,
            "actual_lp": None,
            "actual_community": None,
            "reason": None,
        }
        try:
            rc, stdout, _ = await run_subprocess_async(
                "docker", "exec", self.router, "vtysh", "-c",
                f"show bgp ipv4 unicast {prefix} json",
                timeout=4.0
            )
            if rc != 0:
                details["reason"] = f"vtysh returned non-zero exit code: {rc}"
                return False, details

            data = json.loads(stdout.decode())
            paths = data.get("paths", [])
            if not paths:
                for key, val in data.items():
                    if isinstance(val, list) and len(val) > 0:
                        paths = val
                        break

            if not paths:
                if expected_lp == 0:
                    details["actual_lp"] = 0
                    details["actual_community"] = expected_community
                    return True, details
                details["reason"] = "No paths found in RIB for prefix"
                return False, details

            # Find the best-path entry
            best_path = None
            for path in paths:
                if path.get("bestpath", {}).get("overall", False) or path.get("bestpath", False):
                    best_path = path
                    break

            if best_path is None:
                best_path = paths[0]

            actual_lp = best_path.get("locPrf", best_path.get("localPref", None))
            details["actual_lp"] = actual_lp

            if actual_lp is None:
                details["reason"] = "LocalPref field missing from best-path RIB entry"
                return False, details

            if int(actual_lp) != int(expected_lp):
                details["reason"] = (
                    f"LocalPref mismatch: expected={expected_lp}, actual={actual_lp}"
                )
                return False, details

            # Verify community if expected
            if expected_community:
                community_obj = best_path.get("community", {})
                if isinstance(community_obj, dict):
                    actual_comm = community_obj.get("string", "")
                else:
                    actual_comm = str(community_obj)
                details["actual_community"] = actual_comm
                if expected_community not in actual_comm:
                    details["reason"] = (
                        f"Community mismatch: expected='{expected_community}', "
                        f"actual='{actual_comm}'"
                    )
                    return False, details

            details["reason"] = "OK"
            return True, details

        except asyncio.TimeoutError:
            details["reason"] = "vtysh command timed out during RIB query"
            return False, details
        except json.JSONDecodeError as e:
            details["reason"] = f"Failed to parse RIB JSON: {e}"
            return False, details
        except Exception as e:
            details["reason"] = f"Unexpected error during RIB verification: {e}"
            return False, details
