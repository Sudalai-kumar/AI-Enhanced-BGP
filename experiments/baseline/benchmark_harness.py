"""
Benchmark Harness for Baseline BGP Experiments.
Handles metric computation, variance checks, and statistical summaries across iterations.
"""

import subprocess
import json
import time
import os
import sys
import numpy as np
from typing import Dict, Any, List, Optional, Callable

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.utils.logger import setup_logger
from src.telemetry.storage import TelemetryStorage

logger = setup_logger("benchmark_harness")

def exec_vtysh_json(container: str, command: str) -> Optional[Dict[str, Any]]:
    """Executes a vtysh JSON command inside a given FRR container."""
    try:
        res = subprocess.run(
            ["docker", "exec", container, "vtysh", "-c", f"{command} json"],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout.strip())
    except Exception:
        pass
    return None

def exec_cmd(cmd_list: list) -> tuple:
    """Executes a shell command."""
    res = subprocess.run(cmd_list, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr

def compute_stats(values: List[float]) -> Dict[str, float]:
    """Computes mean, std, median, min, max, and coefficient of variation (variance check)."""
    if not values:
        return {"mean": 0.0, "std": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "cv_percent": 0.0}
    arr = np.array(values)
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    cv = float((std / mean) * 100.0) if mean > 0 else 0.0
    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "median": round(float(np.median(arr)), 4),
        "min": round(float(np.min(arr)), 4),
        "max": round(float(np.max(arr)), 4),
        "cv_percent": round(cv, 2)  # Coefficient of variation < 15% indicates low variance/high stability
    }
