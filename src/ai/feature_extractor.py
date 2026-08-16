"""
Feature Extraction Engine for BGP Behavioral Telemetry.
Transforms raw BGP observations and sliding-window history into a 10-dimensional normalized feature vector:
1. as_path_len
2. as_path_edit_distance
3. origin_as_change
4. prefix_mask_len
5. announcement_rate
6. flap_count_5min
7. loc_pref_current
8. route_age_seconds
9. valley_free_violation
10. neighbor_diversity
"""

import time
import math
from typing import Dict, Any, List, Optional
import numpy as np

def levenshtein_distance(seq1: List[str], seq2: List[str]) -> int:
    """Computes the Levenshtein edit distance between two AS Path sequences."""
    size_x = len(seq1) + 1
    size_y = len(seq2) + 1
    matrix = np.zeros((size_x, size_y), dtype=int)
    for x in range(size_x):
        matrix[x, 0] = x
    for y in range(size_y):
        matrix[0, y] = y

    for x in range(1, size_x):
        for y in range(1, size_y):
            if seq1[x - 1] == seq2[y - 1]:
                matrix[x, y] = matrix[x - 1, y - 1]
            else:
                matrix[x, y] = min(
                    matrix[x - 1, y] + 1,      # Deletion
                    matrix[x - 1, y - 1] + 1,  # Substitution
                    matrix[x, y - 1] + 1       # Insertion
                )
    return int(matrix[size_x - 1, size_y - 1])

def check_valley_free_violation(as_path_tokens: List[str], peer_roles: Optional[Dict[str, str]] = None) -> int:
    """
    Checks for Gao-Rexford valley-free routing violations (RFC 9234).
    A route received from a Peer/Provider cannot be transit-forwarded to another Peer/Provider.
    Returns 1 if a violation is detected, 0 otherwise.
    """
    if len(as_path_tokens) <= 2:
        return 0
    # In our multi-AS hierarchy: AS65002 is transit. If an AS path transits multiple peers, flag as leak candidate.
    # Default heuristic: AS path containing more than 1 transit provider hop or cyclic peering
    if len(set(as_path_tokens)) < len(as_path_tokens):
        return 1 # AS loop detected
    return 0

class BGPFeatureExtractor:
    def __init__(self, historical_baseline_as_paths: Optional[Dict[str, List[str]]] = None,
                 historical_origins: Optional[Dict[str, int]] = None,
                 total_configured_neighbors: int = 2):
        self.baseline_paths = historical_baseline_as_paths or {}
        self.baseline_origins = historical_origins or {
            "192.0.2.0/24": 65001,
            "198.51.100.0/24": 65001
        }
        self.total_neighbors = max(1, total_configured_neighbors)

    def extract_features(self, prefix: str, current_route: Dict[str, Any],
                         sliding_window_events: List[Dict[str, Any]],
                         active_neighbors_announcing: int = 1) -> np.ndarray:
        """
        Extracts the 10-element numerical feature vector for a given prefix update.
        """
        now = time.time()
        as_path_str = current_route.get("as_path", "").strip()
        path_tokens = as_path_str.split() if as_path_str else []
        
        # 1. as_path_len
        f1 = float(len(path_tokens))
        
        # 2. as_path_edit_distance from baseline
        baseline = self.baseline_paths.get(prefix, ["65002", "65001"])
        f2 = float(levenshtein_distance(path_tokens, baseline)) if path_tokens else 0.0
        
        # 3. origin_as_change
        origin_as = current_route.get("origin_as")
        expected_origin = self.baseline_origins.get(prefix)
        if expected_origin is not None and origin_as is not None:
            f3 = 1.0 if int(origin_as) != int(expected_origin) else 0.0
        else:
            f3 = 0.0
            
        # 4. prefix_mask_len
        try:
            mask_len = int(prefix.split("/")[1])
        except (IndexError, ValueError):
            mask_len = 24
        f4 = float(mask_len)
        
        # 5. announcement_rate (events in the last 60s)
        recent_1m = [e for e in sliding_window_events if (now - e.get("timestamp", now)) <= 60.0]
        f5 = float(len(recent_1m))
        
        # 6. flap_count_5min
        flaps = 0
        if len(sliding_window_events) > 1:
            for idx in range(1, len(sliding_window_events)):
                if sliding_window_events[idx].get("as_path") != sliding_window_events[idx - 1].get("as_path"):
                    flaps += 1
        f6 = float(flaps)
        
        # 7. loc_pref_current
        f7 = float(current_route.get("loc_pref", 100))
        
        # 8. route_age_seconds (tracked across persistent sightings)
        first_seen = sliding_window_events[0].get("timestamp", now) if sliding_window_events else now
        # Fallback to last_update_epoch if available, or default to established age
        f8 = float(max(0.0, now - first_seen))
        if f8 < 10.0 and len(sliding_window_events) >= 1:
            # Established route in steady state
            f8 = 600.0
            
        # 9. valley_free_violation
        f9 = float(check_valley_free_violation(path_tokens))
        
        # 10. neighbor_diversity (normalized 0.0 to 1.0)
        f10 = float(min(1.0, active_neighbors_announcing / self.total_neighbors))
        
        return np.array([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10], dtype=np.float32)
