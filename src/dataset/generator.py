"""
Realistic Parameterized BGP Dataset Generator with Overlapping Class Distributions.
Generates training & evaluation records across 4 classes:
  0: Normal
  1: Suspicious (Route Flapping / Minor AS Path Deviations)
  2: Route Leak Candidate (Valley-free violations, unexpected transit loops)
  3: Prefix Hijack Candidate (Unexpected origin AS, sub-prefix deaggregation)

Note on separability:
  Class-discriminative features (origin_as_change, valley_free_violation, prefix_mask_len)
  now have overlapping distributions to prevent artificial perfect-score separability.
  Some hijacks do not change origin; some leaks do not violate valley-free in the
  observed AS path; some normal routes have benign churn.  The resulting classifier
  scores reflect genuine learning difficulty rather than label leakage.

Note on holdout strategy:
  Training and test datasets should be generated with DIFFERENT random_state values
  (e.g. 42 for train, 99 for test) to perform a cross-seed holdout evaluation.
  This is NOT a temporal holdout and does not claim to replicate temporal ordering
  of real BGP events.
"""

import numpy as np
import pandas as pd
from typing import Tuple

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

CLASS_NAMES = {
    0: "Normal",
    1: "Suspicious",
    2: "Route Leak Candidate",
    3: "Prefix Hijack Candidate"
}


def generate_bgp_dataset(n_samples: int = 12000, random_state: int = 42) -> pd.DataFrame:
    """
    Generates a realistic, parameter-jittered BGP dataset with natural class imbalance:
    - 60% Normal (Class 0)
    - 15% Suspicious (Class 1)
    - 10% Route Leak Candidate (Class 2)
    - 15% Prefix Hijack Candidate (Class 3)

    Class distributions intentionally overlap on key features to reflect real-world
    ambiguity (e.g. a legitimate multi-homed AS may change origin; a route leak may
    not always produce a visible valley-free violation at the observation point).
    """
    np.random.seed(random_state)

    n_normal = int(n_samples * 0.60)
    n_suspicious = int(n_samples * 0.15)
    n_leak = int(n_samples * 0.10)
    n_hijack = n_samples - (n_normal + n_suspicious + n_leak)

    data = []

    # ------------------------------------------------------------------
    # 1. Normal Routes (Class 0)
    # ------------------------------------------------------------------
    for _ in range(n_normal):
        f1 = np.random.choice([2, 3, 4], p=[0.7, 0.2, 0.1])            # as_path_len
        f2 = np.random.choice([0, 1], p=[0.85, 0.15])                  # as_path_edit_distance
        # Rare legitimate origin changes (e.g. multi-homing failover)
        f3 = np.random.choice([0.0, 1.0], p=[0.97, 0.03])              # origin_as_change
        f4 = np.random.choice([24, 23, 22, 16], p=[0.7, 0.15, 0.1, 0.05])  # prefix_mask_len
        f5 = np.random.poisson(lam=1.5)                                 # announcements_per_minute
        # Benign path churn — normal routes can flap occasionally
        f6 = np.random.choice([0, 1, 2, 3], p=[0.70, 0.15, 0.10, 0.05])  # flap_count_5min
        f7 = float(np.random.choice([100, 110, 90]))                    # loc_pref_current
        f8 = np.random.uniform(300.0, 7200.0)                           # route_age_seconds
        # Rare topology misclassification (e.g. unusual but valid peering)
        f9 = np.random.choice([0.0, 1.0], p=[0.98, 0.02])              # valley_free_violation
        f10 = np.random.choice([0.5, 1.0], p=[0.3, 0.7])               # neighbor_diversity
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 0])

    # ------------------------------------------------------------------
    # 2. Suspicious Routes (Class 1 — Flapping, minor route churn)
    # ------------------------------------------------------------------
    for _ in range(n_suspicious):
        f1 = np.random.choice([3, 4, 5], p=[0.4, 0.4, 0.2])
        f2 = np.random.choice([1, 2, 3], p=[0.5, 0.3, 0.2])
        f3 = 0.0                                                         # origin stays same
        f4 = np.random.choice([24, 23, 22], p=[0.8, 0.1, 0.1])
        f5 = np.random.uniform(5.0, 20.0)                               # high announcement bursts
        f6 = np.random.randint(3, 12)                                   # elevated flap count
        f7 = float(np.random.choice([100, 80, 50]))
        f8 = np.random.uniform(10.0, 180.0)                             # young / oscillating age
        f9 = 0.0
        f10 = np.random.choice([0.5, 1.0], p=[0.6, 0.4])
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 1])

    # ------------------------------------------------------------------
    # 3. Route Leak Candidates (Class 2 — Valley Free / Path Looping)
    # ------------------------------------------------------------------
    for _ in range(n_leak):
        f1 = np.random.randint(4, 9)                                    # abnormally long path
        f2 = np.random.randint(3, 7)                                    # high edit distance
        f3 = np.random.choice([0.0, 1.0], p=[0.7, 0.3])
        f4 = np.random.choice([24, 23, 22], p=[0.7, 0.2, 0.1])
        f5 = np.random.uniform(2.0, 8.0)
        f6 = np.random.choice([0, 1, 2], p=[0.6, 0.3, 0.1])
        f7 = float(np.random.choice([100, 100, 120]))
        f8 = np.random.uniform(5.0, 300.0)
        # Not all leaks produce a visible valley-free violation at the monitor point
        f9 = np.random.choice([0.0, 1.0], p=[0.20, 0.80])
        f10 = np.random.choice([0.5, 1.0], p=[0.5, 0.5])
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 2])

    # ------------------------------------------------------------------
    # 4. Prefix Hijack Candidates (Class 3 — Rogue Origin / Sub-prefix)
    # ------------------------------------------------------------------
    for _ in range(n_hijack):
        f1 = np.random.choice([1, 2, 3], p=[0.3, 0.5, 0.2])            # direct or 1-hop hijack
        f2 = np.random.randint(2, 5)                                    # distinct path detour
        # Not all hijacks change origin (e.g. forged AS path with same origin)
        f3 = np.random.choice([0.0, 1.0], p=[0.25, 0.75])
        # Not all hijacks use a more-specific prefix
        f4 = np.random.choice([24, 25, 26], p=[0.50, 0.30, 0.20])
        f5 = np.random.uniform(1.0, 10.0)
        f6 = np.random.choice([0, 1, 2], p=[0.7, 0.2, 0.1])
        f7 = float(np.random.choice([100, 150]))
        f8 = np.random.uniform(1.0, 60.0)                               # newly minted attack route
        f9 = np.random.choice([0.0, 1.0], p=[0.8, 0.2])
        f10 = np.random.choice([0.5, 1.0], p=[0.7, 0.3])
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 3])

    df = pd.DataFrame(data, columns=FEATURE_NAMES + ["label"])
    df = df.sample(frac=1.0, random_state=random_state).reset_index(drop=True)
    return df


def generate_false_positive_set(n_samples: int = 1000, random_state: int = 77) -> pd.DataFrame:
    """
    Generates a false-positive challenge set: records that are legitimately Class 0 (Normal)
    but superficially resemble anomalies.  Used to measure false positive rate separately.

    Includes:
    - Legitimate /25 announcements (multi-homed customers with more-specific prefixes)
    - Legitimate origin changes (planned failover, multi-homing)
    - Transient high-flap events from link instability (resolved, not an attack)
    - Low neighbor diversity from single-homed stubs
    """
    np.random.seed(random_state)
    data = []

    # Scenario A: Legitimate /25 more-specific (customer multi-homing)
    n_a = n_samples // 4
    for _ in range(n_a):
        f1 = np.random.choice([2, 3], p=[0.6, 0.4])
        f2 = np.random.choice([0, 1], p=[0.8, 0.2])
        f3 = 0.0
        f4 = np.random.choice([25, 26], p=[0.7, 0.3])   # more-specific but legitimate
        f5 = np.random.poisson(lam=2.0)
        f6 = np.random.choice([0, 1], p=[0.85, 0.15])
        f7 = float(np.random.choice([100, 110]))
        f8 = np.random.uniform(600.0, 7200.0)            # well-established
        f9 = 0.0
        f10 = np.random.choice([0.5, 1.0], p=[0.5, 0.5])
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 0])

    # Scenario B: Legitimate origin change (planned failover/multi-homing)
    n_b = n_samples // 4
    for _ in range(n_b):
        f1 = np.random.choice([2, 3, 4], p=[0.5, 0.3, 0.2])
        f2 = np.random.choice([1, 2], p=[0.7, 0.3])
        f3 = 1.0                                         # origin changed but legitimate
        f4 = np.random.choice([24, 23], p=[0.8, 0.2])
        f5 = np.random.poisson(lam=2.5)
        f6 = np.random.choice([0, 1], p=[0.9, 0.1])
        f7 = float(np.random.choice([100, 90]))
        f8 = np.random.uniform(120.0, 3600.0)
        f9 = 0.0
        f10 = np.random.choice([0.5, 1.0], p=[0.4, 0.6])
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 0])

    # Scenario C: Transient flapping (link instability, not an attack)
    n_c = n_samples // 4
    for _ in range(n_c):
        f1 = np.random.choice([2, 3], p=[0.6, 0.4])
        f2 = np.random.choice([1, 2, 3], p=[0.5, 0.3, 0.2])
        f3 = 0.0
        f4 = np.random.choice([24, 23], p=[0.85, 0.15])
        f5 = np.random.uniform(8.0, 18.0)               # elevated but stabilising
        f6 = np.random.randint(3, 8)                    # flapping but not hijack-level
        f7 = float(np.random.choice([100, 80]))
        f8 = np.random.uniform(30.0, 300.0)
        f9 = 0.0
        f10 = np.random.choice([0.5, 1.0], p=[0.5, 0.5])
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 0])

    # Scenario D: Single-homed stub (low diversity, not suspicious)
    n_d = n_samples - (n_a + n_b + n_c)
    for _ in range(n_d):
        f1 = np.random.choice([2, 3], p=[0.7, 0.3])
        f2 = np.random.choice([0, 1], p=[0.9, 0.1])
        f3 = 0.0
        f4 = np.random.choice([24, 23, 22], p=[0.7, 0.2, 0.1])
        f5 = np.random.poisson(lam=1.0)
        f6 = np.random.choice([0, 1], p=[0.9, 0.1])
        f7 = float(np.random.choice([100, 90]))
        f8 = np.random.uniform(600.0, 7200.0)
        f9 = 0.0
        f10 = 0.5                                        # single peer — low diversity
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 0])

    df = pd.DataFrame(data, columns=FEATURE_NAMES + ["label"])
    df = df.sample(frac=1.0, random_state=random_state).reset_index(drop=True)
    return df
