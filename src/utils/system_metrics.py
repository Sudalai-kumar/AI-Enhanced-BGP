"""System metrics extraction (CPU, Memory) for FRRouting container processes."""

import subprocess
import json
from typing import Dict, Any, Optional

def get_container_stats(container_name: str) -> Dict[str, Any]:
    """
    Extracts CPU % and Memory RSS from docker stats for a given container.
    """
    try:
        cmd = [
            "docker", "stats", container_name,
            "--no-stream",
            "--format", "{{json .}}"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            raw = json.loads(result.stdout.strip())
            return {
                "container": container_name,
                "cpu_perc": raw.get("CPUPerc", "0.00%"),
                "mem_usage": raw.get("MemUsage", "0B / 0B"),
                "mem_perc": raw.get("MemPerc", "0.00%"),
                "pids": raw.get("PIDs", "0")
            }
    except Exception as e:
        pass
    return {
        "container": container_name,
        "cpu_perc": "0.00%",
        "mem_usage": "N/A",
        "mem_perc": "0.00%",
        "pids": "0"
    }
