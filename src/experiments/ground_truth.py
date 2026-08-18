"""
Ground Truth Event Labeling & Scenarios Registry.
Authoritative ground truth for 4-way comparative benchmarking.
"""

from typing import Dict, Any

GROUND_TRUTH_SCENARIOS = {
    "S1": {
        "id": "S1",
        "name": "Synthetic Direct Prefix Hijack",
        "expected_class": 3,
        "expected_class_name": "Prefix Hijack Candidate",
        "target_prefix": "192.0.2.0/24",
        "target_origin": 65004,
        "is_leak": False,
        "is_flap": False,
        "expected_mitigation": "Quarantine (LocalPref 0 + no-export)"
    },
    "S2": {
        "id": "S2",
        "name": "Synthetic Sub-Prefix Hijack (/25)",
        "expected_class": 3,
        "expected_class_name": "Prefix Hijack Candidate",
        "target_prefix": "192.0.2.0/25",
        "target_origin": 65004,
        "is_leak": False,
        "is_flap": False,
        "expected_mitigation": "Quarantine (LocalPref 0 + no-export)"
    },
    "S3": {
        "id": "S3",
        "name": "Synthetic Route Flapping Burst",
        "expected_class": 1,
        "expected_class_name": "Suspicious",
        "target_prefix": "192.0.2.0/24",
        "target_origin": 65001,
        "is_leak": False,
        "is_flap": True,
        "expected_mitigation": "Soft Deprioritization (LocalPref 80)"
    },
    "S4": {
        "id": "S4",
        "name": "Pakistan Telecom / YouTube (2008)",
        "expected_class": 3,
        "expected_class_name": "Prefix Hijack Candidate",
        "target_prefix": "208.65.153.0/24",
        "target_origin": 17557,
        "is_leak": False,
        "is_flap": False,
        "expected_mitigation": "Quarantine (LocalPref 0 + no-export)"
    },
    "S5": {
        "id": "S5",
        "name": "Google / Rostelecom Route Leak (2017)",
        "expected_class": 2,
        "expected_class_name": "Route Leak Candidate",
        "target_prefix": "192.0.2.0/24",
        "target_origin": 15169,
        "is_leak": True,
        "is_flap": False,
        "expected_mitigation": "Quarantine (LocalPref 0 + no-export)"
    },
    "S6": {
        "id": "S6",
        "name": "Cloudflare / Verizon Route Leak (2019)",
        "expected_class": 2,
        "expected_class_name": "Route Leak Candidate",
        "target_prefix": "192.0.2.0/24",
        "target_origin": 13335,
        "is_leak": True,
        "is_flap": False,
        "expected_mitigation": "Quarantine (LocalPref 0 + no-export)"
    }
}
