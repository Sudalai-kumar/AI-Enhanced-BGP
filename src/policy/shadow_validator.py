"""
Shadow Validation Staging Engine with Injectable Clock for Deterministic Testing.
"""

import time
from typing import Dict, Any, Optional, Tuple, Callable
from src.utils.logger import setup_logger

logger = setup_logger("shadow_validator")

class ShadowValidator:
    def __init__(self, shadow_duration_sec: float = 5.0, required_consecutive_ticks: int = 2,
                 min_dwell_sec: float = 10.0, clock: Callable[[], float] = time.time):
        self.shadow_duration = shadow_duration_sec
        self.required_ticks = required_consecutive_ticks
        self.min_dwell = min_dwell_sec
        self.clock = clock
        
        self.shadow_queue: Dict[str, Dict[str, Any]] = {}
        self.last_applied_time: Dict[str, float] = {}

    def submit_observation(self, prefix: str, target_loc_pref: int, target_community: Optional[str],
                           class_id: int, current_live_loc_pref: int = 100) -> Tuple[bool, str]:
        """
        Submits an observation for shadow evaluation using the injected clock.
        """
        now = self.clock()
        
        # 1. Normal state clears shadow staging candidate
        if target_loc_pref == 100 and target_community is None:
            if prefix in self.shadow_queue:
                logger.info(f"[{prefix}] Streak broken by Normal observation. Discarding shadow candidate.")
                del self.shadow_queue[prefix]
            return False, "Normal state: shadow queue cleared"

        # 2. Dwell Time Enforcement
        last_change = self.last_applied_time.get(prefix, 0.0)
        if (now - last_change) < self.min_dwell and target_loc_pref != 0:
            return False, f"Dwell time active ({now - last_change:.1f}s / {self.min_dwell}s). Policy locked."

        # 3. Immediate Quarantine (Hijacks bypass shadow staging)
        if target_loc_pref == 0:
            logger.warning(f"[{prefix}] Immediate Quarantine trigger! Promoting without shadow delay.")
            self.shadow_queue.pop(prefix, None)
            self.last_applied_time[prefix] = now
            return True, "Immediate quarantine promoted"

        # 4. Shadow Queue Evaluation
        if prefix not in self.shadow_queue:
            self.shadow_queue[prefix] = {
                "target_loc_pref": target_loc_pref,
                "target_community": target_community,
                "candidate_class": class_id,
                "start_time": now,
                "streak_count": 1
            }
            return False, "Placed in shadow queue (streak: 1)"
        else:
            entry = self.shadow_queue[prefix]
            if entry["target_loc_pref"] == target_loc_pref:
                entry["streak_count"] += 1
                elapsed = now - entry["start_time"]
                
                if entry["streak_count"] >= self.required_ticks and elapsed >= self.shadow_duration:
                    del self.shadow_queue[prefix]
                    self.last_applied_time[prefix] = now
                    return True, "Shadow validation passed: promoted to live policy"
                else:
                    return False, f"In shadow validation (streak: {entry['streak_count']}/{self.required_ticks}, elapsed: {elapsed:.1f}s)"
            else:
                self.shadow_queue[prefix] = {
                    "target_loc_pref": target_loc_pref,
                    "target_community": target_community,
                    "candidate_class": class_id,
                    "start_time": now,
                    "streak_count": 1
                }
                return False, "Tier changed: streak reset"
