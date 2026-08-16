"""
Behavioural Policy Engine for Autonomous BGP Control Plane Adaptation.
Translates Trust Scores and anomaly classifications into standards-compliant BGP policy:
- Local Preference tiers (100, 80, 50, 0)
- Dual quarantine (LocalPref 0 + BGP community 'no-export')
- Pushes live FRRouting route-map updates via vtysh with graceful soft re-evaluation.
"""

import subprocess
import time
import os
import sys
from typing import Dict, Any, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.utils.logger import setup_logger

logger = setup_logger("policy_engine")

class BGPPolicyEngine:
    def __init__(self, router: str = "as65003", peer_ip: str = "10.0.23.2", route_map_name: str = "RM_IN_AS65002"):
        self.router = router
        self.peer_ip = peer_ip
        self.route_map_name = route_map_name
        self.current_policies: Dict[str, Dict[str, Any]] = {} # prefix -> {loc_pref, community, timestamp}

    def map_trust_to_policy(self, trust_score: float, class_id: int, current_loc_pref: int = 100) -> Tuple[int, Optional[str], str]:
        """
        Maps continuous Trust Score and Class ID to policy actions with Hysteresis:
        Returns: (target_local_pref, community_action, action_description)
        """
        # Quarantine Tier: Class 3 (Hijack) or Trust < 0.25
        if class_id == 3 or trust_score < 0.25:
            return 0, "no-export", "Quarantine (LocalPref 0 + no-export)"

        # Route Leak Tier: Class 2 (Leak) or Trust < 0.55
        if class_id == 2 or trust_score < 0.55:
            return 50, None, "Hard Deprioritization (LocalPref 50)"

        # Suspicious Tier: Class 1 (Suspicious) or Trust in [0.55, 0.80) with Hysteresis
        # To de-escalate back to normal, trust must exceed 0.85
        if current_loc_pref == 100:
            # Entering suspicious requires trust < 0.80
            if trust_score < 0.80:
                return 80, None, "Soft Deprioritization (LocalPref 80)"
            else:
                return 100, None, "Default Baseline (LocalPref 100)"
        else:
            # Currently deprioritized: requires trust >= 0.85 to return to 100
            if trust_score >= 0.85 and class_id == 0:
                return 100, None, "Default Baseline (LocalPref 100)"
            elif trust_score < 0.55:
                return 50, None, "Hard Deprioritization (LocalPref 50)"
            else:
                return 80, None, "Soft Deprioritization (LocalPref 80)"

    def generate_route_map_config(self, prefix_policies: Dict[str, Dict[str, Any]]) -> str:
        """
        Generates clean FRRouting route-map configuration syntax.
        Default sequence 100 permits remaining traffic with default LocalPref 100.
        """
        lines = []
        seq = 10
        
        for pfx, policy in prefix_policies.items():
            loc_pref = policy.get("loc_pref", 100)
            comm = policy.get("community")
            
            lines.append(f"route-map {self.route_map_name} permit {seq}")
            lines.append(f" match ip address prefix-list PL_{seq}")
            lines.append(f" set local-preference {loc_pref}")
            if comm:
                lines.append(f" set community {comm}")
            lines.append("exit")
            seq += 10
            
        # Fallback permit for all other routes
        lines.append(f"route-map {self.route_map_name} permit 1000")
        lines.append(" set local-preference 100")
        lines.append("exit")
        
        return "\n".join(lines)

    def apply_policy(self, prefix_policies: Dict[str, Dict[str, Any]], settle_delay_sec: float = 0.5) -> bool:
        """
        Applies route-map updates to the live FRRouting container via vtysh
        and triggers a graceful soft BGP inbound re-evaluation.
        """
        self.current_policies = prefix_policies.copy()
        
        # Build vtysh command block
        cmd_lines = ["configure terminal"]
        seq = 10
        for pfx in prefix_policies.keys():
            cmd_lines.append(f"ip prefix-list PL_{seq} permit {pfx}")
            seq += 10
            
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
                logger.info(f"[{self.router}] Live policy updated successfully across {len(prefix_policies)} prefixes.")
                time.sleep(settle_delay_sec) # Anti-race settle delay
                return True
            else:
                logger.error(f"[{self.router}] Failed to apply policy via vtysh: {res.stderr}")
                return False
        except Exception as e:
            logger.error(f"[{self.router}] Error applying policy: {e}")
            return False
