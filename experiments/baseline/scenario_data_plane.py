"""
Scenario 5: Data Plane Reachability & Packet Delivery Ratio (PDR).
Measures ICMP packet loss and round-trip time from AS65003 to AS65001 (192.0.2.1)
across normal state and active disruption.
"""

import subprocess
import time
import os
import sys
import re
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from experiments.baseline.benchmark_harness import logger

def measure_pdr(count: int = 15, timeout_sec: int = 1) -> Dict[str, Any]:
    """Sends ICMP echo requests from AS65003 to 192.0.2.1."""
    cmd = [
        "docker", "exec", "as65003",
        "ping", "-c", str(count), "-W", str(timeout_sec), "192.0.2.1"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=count + 5)
        out = res.stdout
        
        # Parse packet loss percentage
        loss_match = re.search(r"(\d+)% packet loss", out)
        loss_pct = float(loss_match.group(1)) if loss_match else 100.0
        pdr_pct = round(100.0 - loss_pct, 2)
        
        # Parse RTT stats
        rtt_match = re.search(r"rtt min/avg/max/mdev = ([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+) ms", out)
        if rtt_match:
            rtt_avg = float(rtt_match.group(2))
        else:
            rtt_avg = 0.0
            
        return {
            "packets_transmitted": count,
            "packet_delivery_ratio_percent": pdr_pct,
            "packet_loss_percent": loss_pct,
            "avg_rtt_ms": rtt_avg
        }
    except Exception as e:
        logger.error(f"Error measuring PDR: {e}")
        return {
            "packets_transmitted": count,
            "packet_delivery_ratio_percent": 0.0,
            "packet_loss_percent": 100.0,
            "avg_rtt_ms": 0.0
        }
