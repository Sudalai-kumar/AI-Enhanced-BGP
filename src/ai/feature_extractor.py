"""
10-Feature Behavioral Extraction Engine for BGP Telemetry.
Features:
0: as_path_len               - AS-PATH Hop Count
1: as_path_edit_distance     - Levenshtein Edit Distance vs baseline path
2: origin_as_change          - 1 if origin AS changed vs baseline, else 0
3: prefix_mask_len           - Prefix CIDR mask length (e.g. 24, 25)
4: announcements_per_minute  - Standardized transition frequency per 60s
5: flap_count_5min           - Pairwise path/origin changes within last 300s
6: loc_pref_current          - Current BGP Local Preference
7: route_age_seconds         - True measured route maturity (seconds)
8: valley_free_violation     - 1 if AS path violates Gao-Rexford business relationships
9: neighbor_diversity        - Ratio of active announcing peers vs total known peers
"""

import time
import numpy as np
from typing import List, Dict, Any, Optional

# Canonical AS Business Relationships: (AS_A, AS_B) -> 'customer-to-provider' | 'provider-to-customer' | 'peer-to-peer'
# In BGP (RFC 9234 / Gao-Rexford):
# - Step 1: Customer-to-Provider (Upward)
# - Step 2: Peer-to-Peer (Lateral, at most 1 hop)
# - Step 3: Provider-to-Customer (Downward)
# Rule: Once a Downward (Provider->Customer) step occurs, the path cannot transition back to Provider or Peer.

AS_RELATIONSHIPS: Dict[tuple, str] = {
    # Internal Testbed Topology: AS65001 (Customer) -> AS65002 (Transit) -> AS65003 (Peer) <-> AS65004 (Peer)
    (65001, 65002): 'customer-to-provider',
    (65002, 65001): 'provider-to-customer',
    (65002, 65003): 'peer-to-peer',
    (65003, 65002): 'peer-to-peer',
    (65003, 65004): 'peer-to-peer',
    (65004, 65003): 'peer-to-peer',
    
    # Historical Incident Relationships
    # Google (AS15169) - Customer of Rostelecom (AS12389)
    (15169, 12389): 'customer-to-provider',
    (12389, 15169): 'provider-to-customer',
    (12389, 65002): 'peer-to-peer',
    (65002, 12389): 'peer-to-peer',
    
    # Cloudflare (AS13335) - Peer; Allegheny (AS396531) - Customer of Verizon (AS701)
    (396531, 701): 'customer-to-provider',
    (701, 396531): 'provider-to-customer',
    (701, 65002): 'peer-to-peer',
    (65002, 701): 'peer-to-peer',
    (13335, 396531): 'peer-to-peer',
    (396531, 13335): 'peer-to-peer',
    
    # Pakistan Telecom (AS17557) & YouTube (AS36561)
    (36561, 65002): 'customer-to-provider',
    (17557, 65002): 'customer-to-provider',
    (65002, 36561): 'provider-to-customer',
    (65002, 17557): 'provider-to-customer'
}

FEATURE_NAMES = [
    "as_path_len",
    "as_path_edit_distance",
    "origin_as_change",
    "prefix_mask_len",
    "announcements_per_minute",
    "flap_count_5min",
    "loc_pref_current",
    "route_age_seconds",
    "valley_free_violation",
    "neighbor_diversity"
]

class BGPFeatureExtractor:
    def __init__(self, baseline_origin_as: int = 65001, baseline_as_path: str = "65002 65001"):
        self.baseline_origin_as = baseline_origin_as
        self.baseline_as_path = baseline_as_path

    @staticmethod
    def levenshtein_distance(s1: List[str], s2: List[str]) -> int:
        """Computes Levenshtein edit distance between two tokenized AS-PATH lists."""
        m, n = len(s1), len(s2)
        dp = np.zeros((m + 1, n + 1), dtype=int)
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return int(dp[m][n])

    @staticmethod
    def check_valley_free_violation(as_path_str: str) -> int:
        """
        Evaluates AS path against Gao-Rexford business relationships (RFC 9234).
        A path is Valley-Free iff it consists of:
          - Zero or more Customer-to-Provider steps (Upward)
          - Followed by at most one Peer-to-Peer step
          - Followed by zero or more Provider-to-Customer steps (Downward)
        Returns: 1 if violation / leak detected, 0 if valid.
        """
        tokens = [int(x) for x in as_path_str.split() if x.isdigit()]
        if len(tokens) <= 1:
            return 0

        # Check for AS loops first
        if len(set(tokens)) < len(tokens):
            return 1

        state = "UPWARD" # States: 'UPWARD', 'PEER', 'DOWNWARD'

        for i in range(len(tokens) - 1):
            hop_a = tokens[i]
            hop_b = tokens[i + 1]
            rel = AS_RELATIONSHIPS.get((hop_a, hop_b), 'unknown')

            if rel == 'customer-to-provider':
                if state in ('PEER', 'DOWNWARD'):
                    # Violation: Attempting to go UP after a lateral peer or downward step
                    return 1
                state = 'UPWARD'
            elif rel == 'peer-to-peer':
                if state in ('PEER', 'DOWNWARD'):
                    # Violation: Multiple peer hops or peer hop after downward transit
                    return 1
                state = 'PEER'
            elif rel == 'provider-to-customer':
                state = 'DOWNWARD'
            else:
                # Default heuristics for unmapped AS hops: long transit loops (>3 hops) flagged
                if len(tokens) >= 4 and i >= 2:
                    return 1

        return 0

    def extract_features(self, prefix: str, current_route: Dict[str, Any],
                         sliding_window_events: List[Dict[str, Any]],
                         active_neighbors_announcing: int = 1,
                         total_known_peers: int = 2) -> np.ndarray:
        """
        Extracts 10 standardized behavioral features.
        Preserves true route age and calculates rolling 5-minute flaps and standardized rates.
        """
        now = time.time()
        
        # 1. AS Path length
        as_path = str(current_route.get("as_path", "")).strip()
        as_path_tokens = as_path.split()
        as_path_len = float(len(as_path_tokens))

        # 2. AS Path edit distance
        baseline_tokens = self.baseline_as_path.split()
        as_path_edit_distance = float(self.levenshtein_distance(as_path_tokens, baseline_tokens))

        # 3. Origin AS change
        origin_as = current_route.get("origin_as")
        if origin_as is None and as_path_tokens:
            try:
                origin_as = int(as_path_tokens[-1])
            except ValueError:
                origin_as = self.baseline_origin_as
        origin_as_change = 1.0 if (origin_as is not None and int(origin_as) != self.baseline_origin_as) else 0.0

        # 4. Prefix mask length
        try:
            prefix_mask_len = float(prefix.split("/")[1])
        except (IndexError, ValueError):
            prefix_mask_len = 24.0

        # 5. Standardized Announcements Per Minute (within last 60s)
        cutoff_60s = now - 60.0
        events_last_60s = [e for e in sliding_window_events if e.get("timestamp", now) >= cutoff_60s]
        # Count actual state transitions
        transitions_60s = 0
        for i in range(1, len(events_last_60s)):
            if (events_last_60s[i].get("as_path") != events_last_60s[i-1].get("as_path") or
                events_last_60s[i].get("origin_as") != events_last_60s[i-1].get("origin_as")):
                transitions_60s += 1
        
        elapsed_sec = max(1.0, (now - sliding_window_events[0].get("timestamp", now))) if sliding_window_events else 1.0
        announcements_per_minute = float((transitions_60s / min(60.0, elapsed_sec)) * 60.0)

        # 6. Flap Count within true Rolling 5-Minute Window (300s)
        cutoff_300s = now - 300.0
        events_last_300s = [e for e in sliding_window_events if e.get("timestamp", now) >= cutoff_300s]
        flap_count_5min = 0.0
        for i in range(1, len(events_last_300s)):
            if (events_last_300s[i].get("as_path") != events_last_300s[i-1].get("as_path") or
                events_last_300s[i].get("origin_as") != events_last_300s[i-1].get("origin_as")):
                flap_count_5min += 1.0

        # 7. Local Preference
        loc_pref_current = float(current_route.get("loc_pref", 100))

        # 8. True Route Age in seconds (never artificially rewritten)
        last_update_epoch = current_route.get("last_update_epoch")
        if last_update_epoch and last_update_epoch > 0:
            route_age_seconds = max(0.0, float(now - last_update_epoch))
        elif sliding_window_events:
            first_seen = sliding_window_events[0].get("timestamp", now)
            route_age_seconds = max(0.0, float(now - first_seen))
        else:
            route_age_seconds = 0.0

        # 9. Valley-free violation check
        valley_free_violation = float(self.check_valley_free_violation(as_path))

        # 10. True Neighbor Diversity Ratio
        neighbor_diversity = float(np.clip(active_neighbors_announcing / max(1, total_known_peers), 0.0, 1.0))

        feature_vector = np.array([
            as_path_len,
            as_path_edit_distance,
            origin_as_change,
            prefix_mask_len,
            announcements_per_minute,
            flap_count_5min,
            loc_pref_current,
            route_age_seconds,
            valley_free_violation,
            neighbor_diversity
        ], dtype=np.float32)

        return feature_vector
