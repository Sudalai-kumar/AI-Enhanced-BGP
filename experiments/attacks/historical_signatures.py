"""
Historical Internet Anomaly Signatures for BGP Replay.
Maps real-world telemetry characteristics to structured BGP event signatures:
1. Pakistan Telecom / YouTube Prefix Hijack (2008) - Sub-prefix deaggregation (/24 vs /22, rogue origin AS17557)
2. Google / Rostelecom Route Leak (2017) - Multi-transit valley-free violation through AS12389
3. Cloudflare / Verizon Route Leak (2019) - Customer-to-peer route leak via AS396531 / AS701
"""

from typing import Dict, Any, List

HISTORICAL_INCIDENTS = {
    "youtube_2008_hijack": {
        "name": "Pakistan Telecom - YouTube Prefix Hijack (2008)",
        "target_prefix": "208.65.153.0/24",
        "legitimate_supernet": "208.65.152.0/22",
        "legitimate_origin": 36561, # YouTube AS
        "injected_origin": 17557,   # Pakistan Telecom AS
        "injected_as_path": "65002 17557",
        "mask_len": 24,
        "is_subprefix": True,
        "ground_truth_class": 3,    # Prefix Hijack Candidate
        "description": "Unauthorized /24 sub-prefix deaggregation by AS17557 capturing traffic meant for AS36561 /22 supernet."
    },
    "google_2017_leak": {
        "name": "Google - Rostelecom Route Leak (2017)",
        "target_prefix": "8.8.8.0/24",
        "legitimate_origin": 15169, # Google AS
        "leaking_transit_as": 12389,# Rostelecom AS
        "injected_origin": 15169,   # Origin AS cryptographically valid!
        "injected_as_path": "65002 12389 12389 15169", # Valley-free violation / transit loop
        "mask_len": 24,
        "is_subprefix": False,
        "ground_truth_class": 2,    # Route Leak Candidate
        "description": "AS12389 leaked 37 major Google prefixes across peer boundaries violating Gao-Rexford valley-free rules."
    },
    "cloudflare_2019_leak": {
        "name": "Cloudflare - Verizon Route Leak (2019)",
        "target_prefix": "104.16.0.0/16",
        "legitimate_origin": 13335, # Cloudflare AS
        "leaking_customer_as": 396531, # Allegheny Technologies
        "injected_origin": 13335,   # Origin AS valid
        "injected_as_path": "65002 701 396531 13335", # Customer-to-Transit leak
        "mask_len": 16,
        "is_subprefix": False,
        "ground_truth_class": 2,    # Route Leak Candidate
        "description": "Small stub network AS396531 leaked Cloudflare routes to Verizon AS701 causing widespread traffic blackholing."
    }
}
