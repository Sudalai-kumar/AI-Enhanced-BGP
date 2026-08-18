"""
Transparent Behavioural Heuristic Detector (Rule-Based Baseline).
Operates over identical 10-feature vector using standardized announcements_per_minute.
"""

import numpy as np
from typing import Dict, Any

class HeuristicDetector:
    def __init__(self):
        pass

    def evaluate(self, feature_vector: np.ndarray) -> Dict[str, Any]:
        """
        Features mapping:
        0: as_path_len, 1: as_path_edit_distance, 2: origin_as_change,
        3: prefix_mask_len, 4: announcements_per_minute, 5: flap_count_5min,
        6: loc_pref_current, 7: route_age_seconds, 8: valley_free_violation,
        9: neighbor_diversity
        """
        as_path_len = feature_vector[0]
        origin_change = feature_vector[2]
        mask_len = feature_vector[3]
        announcements_per_min = feature_vector[4]
        flaps_5min = feature_vector[5]
        valley_free = feature_vector[8]

        # Rule 1: Hijack (Origin mismatch or deaggregated mask length > /24)
        if origin_change > 0.5 or mask_len > 24.0:
            return {
                "detected": True,
                "class_id": 3,
                "class_name": "Prefix Hijack Candidate",
                "target_loc_pref": 0,
                "action": "Quarantine (LocalPref 0)",
                "reason": "Static Rule 1: Origin mismatch or deaggregated mask length > /24"
            }

        # Rule 2: Route Leak (Valley-free violation or long detour path)
        if valley_free > 0.5 or as_path_len >= 5.0:
            return {
                "detected": True,
                "class_id": 2,
                "class_name": "Route Leak Candidate",
                "target_loc_pref": 50,
                "action": "Deprioritize (LocalPref 50)",
                "reason": "Static Rule 2: AS path length >= 5 or valley-free violation"
            }

        # Rule 3: Flapping / Churn (5min Flaps >= 3 or Announcements >= 10/min)
        if flaps_5min >= 3.0 or announcements_per_min >= 10.0:
            return {
                "detected": True,
                "class_id": 1,
                "class_name": "Suspicious",
                "target_loc_pref": 80,
                "action": "Deprioritize (LocalPref 80)",
                "reason": f"Static Rule 3: Flap count ({flaps_5min}) >= 3 or announcement rate >= 10/min"
            }

        # Rule 4: Normal
        return {
            "detected": False,
            "class_id": 0,
            "class_name": "Normal",
            "target_loc_pref": 100,
            "action": "None (LocalPref 100)",
            "reason": "Static Rule 4: All heuristics within normal bounds"
        }
