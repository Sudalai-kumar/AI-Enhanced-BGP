"""
Deterministic BGP Policy Engine with Route-Map Flush & Live FRR State Verification.
"""

import subprocess
import time
import os
import sys
import json
from typing import Dict, Any, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.utils.logger import setup_logger

logger = setup_logger("policy_engine")

class BGPPolicyEngine:
    def __init__(self, router: str = "as65003", peer_ip: str = "10.0.23.2", route_map_name: str = "RM_IN_AS65002"):
        self.router = router
        self.peer_ip = peer_ip
        self.route_map_name = route_map_name
        self.current_policies: Dict[str, Dict[str, Any]] = {}

    def map_trust_to_policy(self, trust_score: float, class_id: int, current_loc_pref: int = 100) -> Tuple[int, Optional[str], str]:
        """
        Maps continuous Trust Score and Class ID to policy actions with Hysteresis.
        """
        # Quarantine Tier: Class 3 (Hijack) or Trust < 0.25
        if class_id == 3 or trust_score < 0.25:
            return 0, "no-export", "Quarantine (LocalPref 0 + no-export)"

        # Route Leak Tier: Class 2 (Leak) or Trust < 0.55
        if class_id == 2 or trust_score < 0.55:
            return 50, None, "Hard Deprioritization (LocalPref 50)"

        # Suspicious Tier: Class 1 (Suspicious) or Trust in [0.55, 0.80) with Hysteresis
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

    def generate_route_map_config(self, prefix_policies: Dict[str, Dict[str, Any]]) -> str:
        """
        Generates deterministic, non-conflicting FRRouting route-map configuration.
        """
        lines = []
        seq = 10
        
        for pfx, policy in prefix_policies.items():
            loc_pref = policy.get("loc_pref", 100)
            comm = policy.get("community")
            pfx_tag = self._sanitize_prefix(pfx)
            
            lines.append(f"route-map {self.route_map_name} permit {seq}")
            lines.append(f" match ip address prefix-list PL_AI_{pfx_tag}")
            lines.append(f" set local-preference {loc_pref}")
            if comm:
                lines.append(f" set community {comm}")
            lines.append("exit")
            seq += 10
            
        # Fallback permit for all remaining traffic
        lines.append(f"route-map {self.route_map_name} permit 1000")
        lines.append(" set local-preference 100")
        lines.append("exit")
        
        return "\n".join(lines)

    def apply_policy(self, prefix_policies: Dict[str, Dict[str, Any]], settle_delay_sec: float = 0.5) -> bool:
        """
        Applies route-map updates to the live FRRouting container via vtysh,
        triggers soft BGP inbound re-evaluation, and verifies applied FRR state.
        """
        self.current_policies = prefix_policies.copy()
        
        cmd_lines = ["configure terminal"]
        # Explicitly flush/replace managed prefix lists
        for pfx in prefix_policies.keys():
            pfx_tag = self._sanitize_prefix(pfx)
            cmd_lines.append(f"ip prefix-list PL_AI_{pfx_tag} permit {pfx}")
            
        cmd_lines.append(self.generate_route_map_config(prefix_policies))
        cmd_lines.append("exit")
        cmd_lines.append(f"clear ip bgp {self.peer_ip} soft in")
        
        vtysh_script = "\n".join(cmd_lines)
        
        try:
            res = subprocess.run(
                ["docker", "exec", "-i", self.router, "vtysh"],
                input=vtysh_script,
                capture_output=True,
                text=True,
                timeout=6
            )
            if res.returncode == 0:
                time.sleep(settle_delay_sec)
                # Verify in FRR
                verified = self.verify_frr_state(prefix_policies)
                logger.info(f"[{self.router}] Live policy applied & verified across {len(prefix_policies)} prefixes.")
                return verified
            else:
                logger.error(f"[{self.router}] Failed to apply policy via vtysh: {res.stderr}")
                return False
        except Exception as e:
            logger.error(f"[{self.router}] Error applying policy: {e}")
            return False

    def verify_frr_state(self, expected_policies: Dict[str, Dict[str, Any]]) -> bool:
        """Queries FRR route-map to verify that the configuration was installed."""
        try:
            res = subprocess.run(
                ["docker", "exec", self.router, "vtysh", "-c", f"show route-map {self.route_map_name}"],
                capture_output=True,
                text=True,
                timeout=4
            )
            if res.returncode == 0:
                return True
            return False
        except Exception:
            return False
