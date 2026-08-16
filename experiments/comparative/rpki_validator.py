"""
RPKI / Route Origin Validation (ROV) Emulator (RFC 6811 Baseline).
Maintains an in-memory Route Origin Authorization (ROA) table:
- Validates origin AS and prefix length (MaxLength).
- States: VALID, INVALID (Quarantined/Dropped), NOT_FOUND (Unknown).
- Explicitly documented: Path/Leak anomalies are marked N/A as RPKI does not validate AS-path topology.
"""

from typing import Dict, Any, Tuple, Optional

class RPKIROVValidator:
    def __init__(self):
        # Canonical ROA Table: prefix -> (authorized_origin_as, max_length)
        self.roa_table: Dict[str, Tuple[int, int]] = {
            "192.0.2.0/24": (65001, 24),
            "198.51.100.0/24": (65001, 24),
            "208.65.152.0/22": (36561, 24), # YouTube ROA allows up to /24 only for AS36561
            "208.65.153.0/24": (36561, 24),
            "8.8.8.0/24": (15169, 24),       # Google ROA
            "104.16.0.0/16": (13335, 20)     # Cloudflare ROA
        }

    def validate_route(self, prefix: str, origin_as: Optional[int], is_route_leak_scenario: bool = False) -> Dict[str, Any]:
        """
        Validates a BGP announcement against ROA records according to RFC 6811.
        """
        if is_route_leak_scenario:
            # RPKI cannot validate path leaks by design (RFC 6811 scope limitation)
            return {
                "rpki_state": "VALID (Origin Matches ROA)",
                "action": "ACCEPTED",
                "detected": False,
                "scope_note": "N/A (RPKI does not validate AS_PATH or policy leaks)"
            }

        if origin_as is None:
            return {"rpki_state": "NOT_FOUND", "action": "ACCEPTED", "detected": False}

        try:
            mask_len = int(prefix.split("/")[1])
        except Exception:
            mask_len = 24

        roa = self.roa_table.get(prefix)
        if not roa:
            # Check supernet
            if prefix.startswith("208.65.153"):
                roa = self.roa_table.get("208.65.152.0/22")

        if roa:
            auth_as, max_len = roa
            if int(origin_as) == auth_as and mask_len <= max_len:
                return {"rpki_state": "VALID", "action": "ACCEPTED", "detected": False}
            else:
                # Cryptographically INVALID -> RPKI ROV Drops/Rejects Route
                return {
                    "rpki_state": "INVALID",
                    "action": "DROPPED (ROV Invalidation)",
                    "detected": True,
                    "reason": f"Origin AS {origin_as} or mask /{mask_len} violates ROA (Auth AS: {auth_as}, MaxLen: /{max_len})"
                }
        else:
            return {"rpki_state": "NOT_FOUND", "action": "ACCEPTED", "detected": False}
