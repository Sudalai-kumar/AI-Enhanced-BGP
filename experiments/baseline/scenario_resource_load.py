"""
Scenario 4: Control-Plane Resource Overhead Profiling.
Continuously samples CPU % and Memory RSS of unmodified FRRouting daemons across steady-state vs active churn.
Note for Week 5-6: This exact profiling method will be reused for measuring the AI control plane agent.
"""

import time
import os
import sys
from typing import Dict, List, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.utils.system_metrics import get_container_stats
from experiments.baseline.benchmark_harness import logger

def parse_cpu(val_str: str) -> float:
    try:
        return float(val_str.replace("%", "").strip())
    except ValueError:
        return 0.0

def parse_mem_mib(val_str: str) -> float:
    try:
        # Format example: "23.41MiB / 7.649GiB"
        part = val_str.split("/")[0].strip()
        if "MiB" in part:
            return float(part.replace("MiB", "").strip())
        elif "KiB" in part:
            return float(part.replace("KiB", "").strip()) / 1024.0
        elif "GiB" in part:
            return float(part.replace("GiB", "").strip()) * 1024.0
    except Exception:
        pass
    return 0.0

def profile_resources(duration_sec: float = 10.0, sample_interval: float = 1.0) -> Dict[str, Any]:
    """Profiles CPU & RAM across all FRR containers."""
    containers = ["as65001", "as65002", "as65003", "as65004"]
    cpu_samples: Dict[str, List[float]] = {c: [] for c in containers}
    mem_samples: Dict[str, List[float]] = {c: [] for c in containers}
    
    start = time.time()
    while time.time() - start < duration_sec:
        for c in containers:
            stats = get_container_stats(c)
            cpu_samples[c].append(parse_cpu(stats.get("cpu_perc", "0%")))
            mem_samples[c].append(parse_mem_mib(stats.get("mem_usage", "0MiB")))
        time.sleep(sample_interval)
        
    summary = {}
    for c in containers:
        c_cpu = cpu_samples[c]
        c_mem = mem_samples[c]
        summary[c] = {
            "avg_cpu_percent": round(sum(c_cpu) / max(len(c_cpu), 1), 3),
            "max_cpu_percent": round(max(c_cpu) if c_cpu else 0.0, 3),
            "avg_mem_mib": round(sum(c_mem) / max(len(c_mem), 1), 2),
            "max_mem_mib": round(max(c_mem) if c_mem else 0.0, 2)
        }
        
    return summary
