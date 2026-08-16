"""
Rollback & State Restoration Manager.
Tracks active policy modifications on live routes and coordinates automatic rollbacks
to baseline LocalPref 100 once behavioral trust recovers.

Features:
- Required recovery streak (M >= 3 consecutive Normal observations)
- Immediate rollback streak cancellation on anomaly regression
"""

import time
from typing import Dict, Any, Optional, Tuple
from src.utils.logger import setup_logger

logger = setup_logger("rollback_manager")

class RollbackManager:
    def __init__(self, required_normal_ticks: int = 3):
        self.required_normal_ticks = required_normal_ticks
        
        # prefix -> {applied_loc_pref, applied_community, modified_timestamp}
        self.active_modifications: Dict[str, Dict[str, Any]] = {}
        
        # prefix -> consecutive normal observation count
        self.recovery_streaks: Dict[str, int] = {}

    def register_policy_modification(self, prefix: str, applied_loc_pref: int, applied_community: Optional[str]):
        """Registers that a non-default policy was applied to this prefix."""
        if applied_loc_pref != 100:
            self.active_modifications[prefix] = {
                "loc_pref": applied_loc_pref,
                "community": applied_community,
                "modified_at": time.time()
            }
            self.recovery_streaks[prefix] = 0
            logger.info(f"[{prefix}] Modification registered: LP={applied_loc_pref}, Comm={applied_community}")
        else:
            # Reverted to normal
            self.active_modifications.pop(prefix, None)
            self.recovery_streaks.pop(prefix, None)

    def process_observation(self, prefix: str, is_normal: bool) -> Tuple[bool, str]:
        """
        Evaluates normal vs anomalous observation for an actively modified prefix.
        Returns: (should_trigger_rollback, status_string)
        """
        if prefix not in self.active_modifications:
            return False, "Prefix not under active policy override"

        if is_normal:
            self.recovery_streaks[prefix] = self.recovery_streaks.get(prefix, 0) + 1
            streak = self.recovery_streaks[prefix]
            logger.info(f"[{prefix}] Recovery streak: {streak}/{self.required_normal_ticks} Normal observations.")
            
            if streak >= self.required_normal_ticks:
                logger.info(f"[{prefix}] Normal behavior sustained! Triggering Autonomous Rollback to LocalPref 100.")
                self.register_policy_modification(prefix, 100, None)
                return True, "Rollback criteria satisfied: restore to LP 100"
            else:
                return False, f"In recovery monitoring ({streak}/{self.required_normal_ticks})"
        else:
            # Anomaly re-occurred! Reset recovery streak immediately
            if self.recovery_streaks.get(prefix, 0) > 0:
                logger.warning(f"[{prefix}] Anomaly observed during recovery. Resetting recovery streak to 0.")
                self.recovery_streaks[prefix] = 0
            return False, "Anomaly persisted: rollback canceled"
