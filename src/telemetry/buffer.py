"""
In-memory sliding-window telemetry buffer using Python collections.deque.
Maintains recent routing observations and enables fast extraction of temporal statistics
such as flap count, AS path volatility, and advertisement bursts.
"""

from collections import deque, defaultdict
import time
from typing import Dict, List, Any, Optional

class SlidingWindowBuffer:
    def __init__(self, window_size: int = 50, time_window_seconds: float = 300.0):
        """
        :param window_size: Max number of history items per prefix.
        :param time_window_seconds: Time horizon (e.g. 5 mins) to retain for rate calculations.
        """
        self.window_size = window_size
        self.time_window_seconds = time_window_seconds
        # prefix -> deque of event dicts
        self.buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.window_size))
        # track flap counts and state history
        self.flaps: Dict[str, int] = defaultdict(int)

    def append(self, prefix: str, event_data: Dict[str, Any]):
        """Adds a new observation for a given prefix."""
        record = {
            "timestamp": event_data.get("timestamp", time.time()),
            "as_path": event_data.get("as_path", ""),
            "origin_as": event_data.get("origin_as"),
            "nexthop": event_data.get("nexthop"),
            "loc_pref": event_data.get("loc_pref", 100),
            "med": event_data.get("med", 0),
            "status": event_data.get("status", "ACTIVE")
        }
        
        # Flap detection logic: check if path or origin AS changed from the previous entry
        buf = self.buffers[prefix]
        if len(buf) > 0:
            last = buf[-1]
            if last["as_path"] != record["as_path"] or last["origin_as"] != record["origin_as"]:
                self.flaps[prefix] += 1

        buf.append(record)

    def get_history(self, prefix: str) -> List[Dict[str, Any]]:
        """Returns the recent history list for a prefix."""
        return list(self.buffers[prefix])

    def get_prefix_features(self, prefix: str) -> Dict[str, Any]:
        """
        Extracts temporal and behavioral summary statistics for a given prefix.
        Used by the Week 5-6 ML Feature Extractor.
        """
        buf = self.buffers.get(prefix, deque())
        if not buf:
            return {
                "count": 0,
                "flap_count": 0,
                "unique_as_paths": 0,
                "unique_origins": 0,
                "advertisement_rate": 0.0,
                "latest_as_path_len": 0
            }

        now = time.time()
        recent_events = [e for e in buf if (now - e["timestamp"]) <= self.time_window_seconds]
        
        unique_paths = set(e["as_path"] for e in buf)
        unique_origins = set(e["origin_as"] for e in buf if e["origin_as"] is not None)
        
        duration = (now - buf[0]["timestamp"]) if len(buf) > 1 else 1.0
        adv_rate = len(recent_events) / max(duration, 1.0)
        latest_path = buf[-1]["as_path"].split() if buf[-1]["as_path"] else []

        return {
            "count": len(buf),
            "flap_count": self.flaps[prefix],
            "unique_as_paths": len(unique_paths),
            "unique_origins": len(unique_origins),
            "advertisement_rate": adv_rate,
            "latest_as_path_len": len(latest_path),
            "latest_origin_as": buf[-1]["origin_as"],
            "latest_loc_pref": buf[-1]["loc_pref"]
        }
