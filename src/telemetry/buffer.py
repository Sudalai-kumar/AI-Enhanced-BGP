"""
Sliding Window Telemetry Buffer with Real Time-Window Calculations.
Stores recent BGP updates per prefix, discarding stale events outside the temporal cutoff.
"""

from collections import deque
from typing import Dict, Any, List
import time

class SlidingWindowBuffer:
    def __init__(self, window_size: int = 100, time_window_seconds: float = 300.0):
        self.window_size = window_size
        self.time_window_seconds = time_window_seconds
        # prefix -> deque of event dicts
        self.buffer: Dict[str, deque] = {}

    def add_event(self, prefix: str, event: Dict[str, Any]):
        """Appends a new event and trims events older than the time window."""
        now = time.time()
        if "timestamp" not in event:
            event["timestamp"] = now

        if prefix not in self.buffer:
            self.buffer[prefix] = deque(maxlen=self.window_size)

        self.buffer[prefix].append(event)
        self._trim_stale(prefix, now)

    def _trim_stale(self, prefix: str, now: float):
        """Removes entries older than time_window_seconds."""
        if prefix not in self.buffer:
            return
        cutoff = now - self.time_window_seconds
        q = self.buffer[prefix]
        while q and q[0].get("timestamp", now) < cutoff:
            q.popleft()

    def get_history(self, prefix: str, window_seconds: float = None) -> List[Dict[str, Any]]:
        """Returns the list of historical observations within the requested time window."""
        if prefix not in self.buffer:
            return []
        now = time.time()
        self._trim_stale(prefix, now)
        
        events = list(self.buffer[prefix])
        if window_seconds is not None:
            cutoff = now - window_seconds
            events = [e for e in events if e.get("timestamp", now) >= cutoff]
        return events

    def count_flaps(self, prefix: str, window_seconds: float = 300.0) -> int:
        """Computes true rolling pairwise path/origin transitions within the window."""
        history = self.get_history(prefix, window_seconds=window_seconds)
        if len(history) < 2:
            return 0
        
        flaps = 0
        for i in range(1, len(history)):
            prev_path = history[i-1].get("as_path")
            cur_path = history[i].get("as_path")
            prev_orig = history[i-1].get("origin_as")
            cur_orig = history[i].get("origin_as")
            
            if prev_path != cur_path or prev_orig != cur_orig:
                flaps += 1
        return flaps

    def clear(self):
        """Clears all buffered entries."""
        self.buffer.clear()
