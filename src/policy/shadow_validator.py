"""
Shadow Validation Staging Engine.
Holds proposed policy adjustments in a transient buffer to verify behavioral consistency
and prevent false-positive route flapping.

Features:
- N consecutive tick requirement (T_shadow = 5.0s, N=2)
- Strict streak-breaking on normal/contradictory ticks
- Minimum dwell time enforcement (T_dwell = 10.0s)
"""

import time
from typing import Dict, Any, Optional, Tuple
from src.utils.logger import setup_logger

logger = setup_logger("shadow_validator")

class ShadowValidator:
    def __init__(self, shadow_duration_sec: float = 5.0, required_consecutive_ticks: int = 2, min_dwell_sec: float = 10.0):
        self.shadow_duration = shadow_duration_sec
        self.required_ticks = required_consecutive_ticks
        self.min_dwell = min_dwell_sec
        
        # prefix -> {target_loc_pref, target_community, start_time, streak_count, candidate_class}
        self.shadow_queue: Dict[str, Dict[str, Any]] = {}
        
        # prefix -> timestamp of last live policy change
        self.last_applied_time: Dict[str, float] = {}

    def submit_observation(self, prefix: str, target_loc_pref: int, target_community: Optional[str],
                           class_id: int, current_live_loc_pref: int = 100) -> Tuple[bool, str]:
        """
        Submits an observation for shadow evaluation.
        Returns: (should_promote_to_live, reason_string)
        """
        now = time.time()
        
        # 1. Check if route is in Normal state (no intervention needed)
        if target_loc_pref == 100 and target_community is None:
            if prefix in self.shadow_queue:
                logger.info(f"[{prefix}] Streak broken by Normal observation. Discarding shadow staging candidate.")
                del self.shadow_queue[prefix]
            return False, "Normal state: shadow queue cleared"

        # 2. Check Dwell Time: prevent thrashing unless escalating directly to Quarantine (LP 0)
        last_change = self.last_applied_time.get(prefix, 0.0)
        if (now - last_change) < self.min_dwell and target_loc_pref != 0:
            return False, f"Dwell time active ({now - last_change:.1f}s / {self.min_dwell}s). Policy locked."

        # 3. Process Shadow Queue Candidate
        if target_loc_pref == 0:
            # Immediate Quarantine (Hijack): promote immediately
            logger.warning(f"[{prefix}] Immediate Quarantine trigger! Promoting to live policy without shadow delay.")
            self.shadow_queue.pop(prefix, None)
            self.last_applied_time[prefix] = now
            return True, "Immediate quarantine promoted"

        if prefix not in self.shadow_queue:
            # Brand new candidate
            self.shadow_queue[prefix] = {
                "target_loc_pref": target_loc_pref,
                "target_community": target_community,
                "candidate_class": class_id,
                "start_time": now,
                "streak_count": 1
            }
            logger.info(f"[{prefix}] Placed in Shadow Validation queue (Target LP: {target_loc_pref}, Streak: 1/{self.required_ticks}).")
            return False, "Placed in shadow queue (streak: 1)"
        else:
            entry = self.shadow_queue[prefix]
            # Check if current observation matches candidate tier
            if entry["target_loc_pref"] == target_loc_pref:
                entry["streak_count"] += 1
                elapsed = now - entry["start_time"]
                
                # Check Promotion Criteria: N consecutive ticks AND elapsed >= T_shadow (or immediate for Hijack)
                if (entry["streak_count"] >= self.required_ticks and elapsed >= self.shadow_duration) or target_loc_pref == 0:
                    logger.info(f"[{prefix}] Shadow Validation Confirmed ({entry['streak_count']} ticks, {elapsed:.1f}s). Promoting to live policy!")
                    del self.shadow_queue[prefix]
                    self.last_applied_time[prefix] = now
                    return True, "Shadow validation passed: promoted to live policy"
                else:
                    return False, f"In shadow validation (streak: {entry['streak_count']}/{self.required_ticks}, elapsed: {elapsed:.1f}s)"
            else:
                # Contradictory anomaly tier -> reset streak to new tier
                logger.warning(f"[{prefix}] Shadow candidate changed tier ({entry['target_loc_pref']} -> {target_loc_pref}). Resetting streak.")
                self.shadow_queue[prefix] = {
                    "target_loc_pref": target_loc_pref,
                    "target_community": target_community,
                    "candidate_class": class_id,
                    "start_time": now,
                    "streak_count": 1
                }
                return False, "Tier changed: streak reset"
