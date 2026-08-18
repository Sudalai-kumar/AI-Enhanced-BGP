"""
Multi-Criteria Rollback & State Restoration Manager.
Requires:
1. Normal classification for M >= 3 consecutive ticks.
2. Stable AS Path & Origin (origin_change=0, valley_free=0).
3. Flap Quiescence (recent flaps=0).
4. Verified FRR Next-Hop Reachability.
"""

import time
from typing import Dict, Any, Optional, Tuple
from src.utils.logger import setup_logger

logger = setup_logger("rollback_manager")

class RollbackManager:
    def __init__(self, required_normal_ticks: int = 3):
        self.required_normal_ticks = required_normal_ticks
        self.active_modifications: Dict[str, Dict[str, Any]] = {}
        self.recovery_streaks: Dict[str, int] = {}

    def register_policy_modification(self, prefix: str, applied_loc_pref: int, applied_community: Optional[str]):
        """Registers a non-default policy override."""
        if applied_loc_pref != 100:
            self.active_modifications[prefix] = {
                "loc_pref": applied_loc_pref,
                "community": applied_community,
                "modified_at": time.time()
            }
            self.recovery_streaks[prefix] = 0
            logger.info(f"[{prefix}] Override registered: LP={applied_loc_pref}, Comm={applied_community}")
        else:
            self.active_modifications.pop(prefix, None)
            self.recovery_streaks.pop(prefix, None)

    def process_observation(self, prefix: str, is_normal: bool,
                            origin_stable: bool = True,
                            path_stable: bool = True,
                            flaps_quiescent: bool = True,
                            frr_reachable: bool = True) -> Tuple[bool, str]:
        """
        Evaluates multi-criteria recovery for actively modified prefix.
        Returns: (should_trigger_rollback, status_string)
        """
        if prefix not in self.active_modifications:
            return False, "Prefix not under active policy override"

        # Multi-Criteria Health Gate
        network_healthy = is_normal and origin_stable and path_stable and flaps_quiescent and frr_reachable

        if network_healthy:
            self.recovery_streaks[prefix] = self.recovery_streaks.get(prefix, 0) + 1
            streak = self.recovery_streaks[prefix]
            logger.info(f"[{prefix}] Multi-criteria recovery streak: {streak}/{self.required_normal_ticks}.")
            
            if streak >= self.required_normal_ticks:
                logger.info(f"[{prefix}] Full network recovery sustained! Triggering Autonomous Rollback to LocalPref 100.")
                self.register_policy_modification(prefix, 100, None)
                return True, "Rollback criteria satisfied: restore to LP 100"
            else:
                return False, f"In multi-criteria recovery ({streak}/{self.required_normal_ticks})"
        else:
            # Anomaly or network instability observed -> reset recovery streak
            if self.recovery_streaks.get(prefix, 0) > 0:
                logger.warning(f"[{prefix}] Network instability observed during recovery. Resetting streak to 0.")
                self.recovery_streaks[prefix] = 0
            return False, "Network not fully healthy: rollback streak held at 0"
