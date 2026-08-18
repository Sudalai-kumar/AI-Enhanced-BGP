"""
Realistic Parameterized BGP Dataset Generator with Noise Injection.
Generates training & evaluation records across 4 classes:
  0: Normal
  1: Suspicious (Route Flapping / Minor AS Path Deviations)
  2: Route Leak Candidate (Valley-free violations, unexpected transit loops)
  3: Prefix Hijack Candidate (Unexpected origin AS, sub-prefix deaggregation)
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
    """
    np.random.seed(random_state)
    
    n_normal = int(n_samples * 0.60)
    n_suspicious = int(n_samples * 0.15)
    n_leak = int(n_samples * 0.10)
    n_hijack = n_samples - (n_normal + n_suspicious + n_leak)
    
    data = []
    
    # -------------------------------------------------------------
    # 1. Normal Routes (Class 0)
    # -------------------------------------------------------------
    for _ in range(n_normal):
        f1 = np.random.choice([2, 3, 4], p=[0.7, 0.2, 0.1])       # as_path_len
        f2 = np.random.choice([0, 1], p=[0.85, 0.15])             # as_path_edit_distance (minor benign variance)
        f3 = 0.0                                                   # origin_as_change = 0
        f4 = np.random.choice([24, 23, 22, 16], p=[0.7, 0.15, 0.1, 0.05]) # prefix_mask_len
        f5 = np.random.poisson(lam=1.5)                            # announcement_rate
        f6 = np.random.choice([0, 1], p=[0.9, 0.1])               # flap_count_5min
        f7 = float(np.random.choice([100, 110, 90]))              # loc_pref
        f8 = np.random.uniform(300.0, 7200.0)                     # route_age_seconds (well established)
        f9 = 0.0                                                   # valley_free_violation
        f10 = np.random.choice([0.5, 1.0], p=[0.3, 0.7])          # neighbor_diversity
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 0])
        
    # -------------------------------------------------------------
    # 2. Suspicious Routes (Class 1 - Flapping, minor route churn)
    # -------------------------------------------------------------
    for _ in range(n_suspicious):
        f1 = np.random.choice([3, 4, 5], p=[0.4, 0.4, 0.2])
        f2 = np.random.choice([1, 2, 3], p=[0.5, 0.3, 0.2])
        f3 = 0.0                                                   # origin stays same
        f4 = np.random.choice([24, 23, 22], p=[0.8, 0.1, 0.1])
        f5 = np.random.uniform(5.0, 20.0)                          # high announcement bursts
        f6 = np.random.randint(3, 12)                              # elevated flap count
        f7 = float(np.random.choice([100, 80, 50]))
        f8 = np.random.uniform(10.0, 180.0)                       # young / oscillating age
        f9 = 0.0
        f10 = np.random.choice([0.5, 1.0], p=[0.6, 0.4])
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 1])
        
    # -------------------------------------------------------------
    # 3. Route Leak Candidates (Class 2 - Valley Free / Path Looping)
    # -------------------------------------------------------------
    for _ in range(n_leak):
        f1 = np.random.randint(4, 9)                               # abnormally long path
        f2 = np.random.randint(3, 7)                               # high edit distance
        f3 = np.random.choice([0.0, 1.0], p=[0.7, 0.3])          # may or may not change origin
        f4 = np.random.choice([24, 23, 22], p=[0.7, 0.2, 0.1])
        f5 = np.random.uniform(2.0, 8.0)
        f6 = np.random.choice([0, 1, 2], p=[0.6, 0.3, 0.1])
        f7 = float(np.random.choice([100, 100, 120]))
        f8 = np.random.uniform(5.0, 300.0)
        f9 = 1.0                                                   # valley-free violation detected
        f10 = np.random.choice([0.5, 1.0], p=[0.5, 0.5])
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 2])
        
    # -------------------------------------------------------------
    # 4. Prefix Hijack Candidates (Class 3 - Rogue Origin / Sub-prefix)
    # -------------------------------------------------------------
    for _ in range(n_hijack):
        f1 = np.random.choice([1, 2, 3], p=[0.3, 0.5, 0.2])       # direct or 1-hop hijack
        f2 = np.random.randint(2, 5)                               # distinct path detour
        f3 = 1.0                                                   # origin AS changed!
        f4 = np.random.choice([24, 25, 26], p=[0.5, 0.3, 0.2])    # more specific sub-prefix deaggregation
        f5 = np.random.uniform(1.0, 10.0)
        f6 = np.random.choice([0, 1, 2], p=[0.7, 0.2, 0.1])
        f7 = float(np.random.choice([100, 150]))                  # often elevated loc_pref
        f8 = np.random.uniform(1.0, 60.0)                         # newly minted attack route
        f9 = np.random.choice([0.0, 1.0], p=[0.8, 0.2])
        f10 = np.random.choice([0.5, 1.0], p=[0.7, 0.3])
        data.append([f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, 3])
        
    df = pd.DataFrame(data, columns=FEATURE_NAMES + ["label"])
    # Shuffle the dataset
    df = df.sample(frac=1.0, random_state=random_state).reset_index(drop=True)
    return df
