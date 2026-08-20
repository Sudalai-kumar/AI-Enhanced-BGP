"""
Live MTTD / MTTM Benchmark Harness for the AI-Enhanced BGP Controller.

This script measures detection and mitigation latency end-to-end by:
  1. Starting (or attaching to) the AutonomousBGPController subprocess.
  2. Injecting each attack scenario via existing attack scripts or inject_failure.py.
  3. Polling the detection_events SQLite table (written by the controller) every 100ms.
  4. Recording MTTD = detected_at - t0 and MTTM = mitigated_at - t0 independently.
  5. Repeating each scenario N trials and reporting mean +/- std.
  6. Writing results to experiments/results/live_benchmark_results.json.

Evidence level of output: EMPIRICAL (live FRR testbed measurement).
In --dry-run mode, returns previously documented values labelled MODELLED.

Requirements: Docker + running FRR topology (docker compose up -d).
"""

import argparse
import json
import os
import subprocess
import sys
import time
import statistics
import sqlite3
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DB_PATH = os.path.join(_REPO_ROOT, "data", "controller_state.db")
_RESULTS_DIR = os.path.join(_REPO_ROOT, "experiments", "results")
_ATTACKS_DIR = os.path.join(_REPO_ROOT, "experiments", "attacks")

# --- Scenario definitions --------------------------------------------------
# Each scenario specifies the prefix being attacked and the attack script to run.
# The attack script is called as a subprocess with no arguments; it is expected
# to inject the attack and return immediately.
SCENARIO_REGISTRY: Dict[str, Dict[str, Any]] = {
    "S1": {
        "name": "Synthetic Direct Prefix Hijack",
        "prefix": "192.0.2.0/24",
        "attack_script": os.path.join(_ATTACKS_DIR, "inject_direct_hijack.py"),
        "scenario_type": "synthetic",
    },
    "S2": {
        "name": "Synthetic Sub-Prefix Hijack (/25)",
        "prefix": "192.0.2.0/25",
        "attack_script": os.path.join(_ATTACKS_DIR, "inject_subprefix_hijack.py"),
        "scenario_type": "synthetic",
    },
    "S3": {
        "name": "Synthetic Route Flapping Burst",
        "prefix": "192.0.2.0/24",
        "attack_script": os.path.join(_ATTACKS_DIR, "inject_flapping.py"),
        "scenario_type": "synthetic",
    },
    "S4": {
        "name": "Pakistan Telecom / YouTube (2008) — Topology-Local Replay",
        "prefix": "208.65.153.0/24",
        "attack_script": os.path.join(_ATTACKS_DIR, "inject_direct_hijack.py"),
        "scenario_type": "topology-local behavioral replay",
        "scenario_note": (
            "This scenario recreates the behavioral signature of the named historical incident "
            "(origin hijack pattern) within the four-AS FRR laboratory topology. "
            "It is NOT a reproduction of the actual Internet-scale event."
        ),
    },
    "S5": {
        "name": "Google / Rostelecom Route Leak (2017) — Topology-Local Replay",
        "prefix": "192.0.2.0/24",
        "attack_script": os.path.join(_ATTACKS_DIR, "inject_route_leak.py"),
        "scenario_type": "topology-local behavioral replay",
        "scenario_note": (
            "This scenario recreates the behavioral signature of the named historical incident "
            "(valley-free violation / route leak pattern) within the four-AS FRR laboratory topology. "
            "It is NOT a reproduction of the actual Internet-scale event."
        ),
    },
    "S6": {
        "name": "Cloudflare / Verizon Route Leak (2019) — Topology-Local Replay",
        "prefix": "192.0.2.0/24",
        "attack_script": os.path.join(_ATTACKS_DIR, "inject_route_leak.py"),
        "scenario_type": "topology-local behavioral replay",
        "scenario_note": (
            "This scenario recreates the behavioral signature of the named historical incident "
            "(large-scale route leak pattern) within the four-AS FRR laboratory topology. "
            "It is NOT a reproduction of the actual Internet-scale event."
        ),
    },
}

# --- Modelled fallback values (used in --dry-run mode) ---------------------
MODELLED_VALUES: Dict[str, Dict[str, Any]] = {
    "S1": {"mttd_mean": 1.34, "mttd_std": 0.08, "mttm_mean": 1.34, "mttm_std": 0.08},
    "S2": {"mttd_mean": 4.92, "mttd_std": 0.12, "mttm_mean": 4.92, "mttm_std": 0.12},
    "S3": {"mttd_mean": 15.42, "mttd_std": 0.45, "mttm_mean": 15.42, "mttm_std": 0.45},
    "S4": {"mttd_mean": 4.93, "mttd_std": 0.15, "mttm_mean": 4.93, "mttm_std": 0.15},
    "S5": {"mttd_mean": 1.54, "mttd_std": 0.09, "mttm_mean": 1.54, "mttm_std": 0.09},
    "S6": {"mttd_mean": 1.49, "mttd_std": 0.07, "mttm_mean": 1.49, "mttm_std": 0.07},
}


def _poll_detection(prefix: str, t0: float, timeout_sec: float = 60.0,
                    poll_interval: float = 0.1) -> Optional[float]:
    """
    Polls the detection_events table until a row appears for prefix with
    detected_at > t0.  Returns detected_at, or None if timeout expires.
    """
    deadline = t0 + timeout_sec
    while time.time() < deadline:
        try:
            with sqlite3.connect(_DB_PATH) as conn:
                row = conn.execute(
                    "SELECT detected_at FROM detection_events "
                    "WHERE prefix = ? AND detected_at > ? "
                    "ORDER BY detected_at DESC LIMIT 1",
                    (prefix, t0)
                ).fetchone()
                if row:
                    return row[0]
        except Exception:
            pass
        time.sleep(poll_interval)
    return None


def _poll_mitigation(prefix: str, t0: float, timeout_sec: float = 60.0,
                     poll_interval: float = 0.1) -> Optional[float]:
    """
    Polls the detection_events table until mitigated_at is set for the most
    recent open detection row for prefix after t0.  Returns mitigated_at.
    """
    deadline = t0 + timeout_sec
    while time.time() < deadline:
        try:
            with sqlite3.connect(_DB_PATH) as conn:
                row = conn.execute(
                    "SELECT mitigated_at FROM detection_events "
                    "WHERE prefix = ? AND detected_at > ? AND mitigated_at IS NOT NULL "
                    "ORDER BY detected_at DESC LIMIT 1",
                    (prefix, t0)
                ).fetchone()
                if row:
                    return row[0]
        except Exception:
            pass
        time.sleep(poll_interval)
    return None


def _inject_attack(script_path: str) -> bool:
    """Runs the attack script as a subprocess. Returns True on success."""
    if not os.path.exists(script_path):
        print(f"  [!] Attack script not found: {script_path}")
        return False
    result = subprocess.run([sys.executable, script_path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"  [!] Attack script failed: {result.stderr.strip()}")
        return False
    return True


def _reset_scenario(prefix: str):
    """Brief pause to allow routing state to stabilise between trials."""
    time.sleep(5.0)


def run_live_scenario(scenario_id: str, scenario: Dict[str, Any],
                      n_trials: int = 5, timeout_sec: float = 60.0) -> Dict[str, Any]:
    """Measures MTTD and MTTM for a scenario over n_trials trials."""
    print(f"\n[*] Running scenario {scenario_id}: {scenario['name']}")
    mttd_samples: List[float] = []
    mttm_samples: List[float] = []

    for trial in range(1, n_trials + 1):
        print(f"  Trial {trial}/{n_trials}...", end=" ", flush=True)
        t0 = time.time()

        ok = _inject_attack(scenario["attack_script"])
        if not ok:
            print(f"SKIP (attack injection failed)")
            continue

        detected_at = _poll_detection(scenario["prefix"], t0, timeout_sec=timeout_sec)
        if detected_at is None:
            print(f"TIMEOUT (no detection within {timeout_sec}s)")
            _reset_scenario(scenario["prefix"])
            continue

        mitigated_at = _poll_mitigation(scenario["prefix"], t0, timeout_sec=timeout_sec)
        if mitigated_at is None:
            print(f"TIMEOUT (detection at {detected_at - t0:.2f}s but no mitigation)")
            _reset_scenario(scenario["prefix"])
            continue

        mttd = detected_at - t0
        mttm = mitigated_at - t0
        mttd_samples.append(mttd)
        mttm_samples.append(mttm)
        print(f"MTTD={mttd:.2f}s  MTTM={mttm:.2f}s")
        _reset_scenario(scenario["prefix"])

    if not mttd_samples:
        return {
            "scenario_id": scenario_id,
            "name": scenario["name"],
            "scenario_type": scenario.get("scenario_type", "synthetic"),
            "scenario_note": scenario.get("scenario_note", ""),
            "evidence_level": "EMPIRICAL",
            "trials_attempted": n_trials,
            "trials_successful": 0,
            "error": "No successful trials"
        }

    result = {
        "scenario_id": scenario_id,
        "name": scenario["name"],
        "scenario_type": scenario.get("scenario_type", "synthetic"),
        "scenario_note": scenario.get("scenario_note", ""),
        "evidence_level": "EMPIRICAL",
        "trials_attempted": n_trials,
        "trials_successful": len(mttd_samples),
        "mttd_mean_sec": round(statistics.mean(mttd_samples), 4),
        "mttd_std_sec": round(statistics.stdev(mttd_samples) if len(mttd_samples) > 1 else 0.0, 4),
        "mttd_median_sec": round(statistics.median(mttd_samples), 4),
        "mttm_mean_sec": round(statistics.mean(mttm_samples), 4),
        "mttm_std_sec": round(statistics.stdev(mttm_samples) if len(mttm_samples) > 1 else 0.0, 4),
        "mttm_median_sec": round(statistics.median(mttm_samples), 4),
        "mttd_lt_mttm_all_trials": all(d <= m for d, m in zip(mttd_samples, mttm_samples)),
    }
    print(f"  Summary: MTTD={result['mttd_mean_sec']:.2f}+/-{result['mttd_std_sec']:.2f}s  "
          f"MTTM={result['mttm_mean_sec']:.2f}+/-{result['mttm_std_sec']:.2f}s")
    return result


def run_dry_run(scenario_ids: List[str]) -> List[Dict[str, Any]]:
    """Returns previously documented modelled values for offline use."""
    results = []
    for sid in scenario_ids:
        sc = SCENARIO_REGISTRY.get(sid, {})
        mv = MODELLED_VALUES.get(sid, {})
        results.append({
            "scenario_id": sid,
            "name": sc.get("name", sid),
            "scenario_type": sc.get("scenario_type", "synthetic"),
            "scenario_note": sc.get("scenario_note", ""),
            "evidence_level": "MODELLED",
            "evidence_note": (
                "Dry-run mode: values are previously documented estimates, not live measurements. "
                "Run without --dry-run on a live FRR testbed to obtain EMPIRICAL measurements."
            ),
            "mttd_mean_sec": mv.get("mttd_mean"),
            "mttd_std_sec": mv.get("mttd_std"),
            "mttm_mean_sec": mv.get("mttm_mean"),
            "mttm_std_sec": mv.get("mttm_std"),
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="Live MTTD/MTTM Benchmark for AI-Enhanced BGP")
    parser.add_argument(
        "--scenarios", default="S1,S2,S3,S4,S5,S6",
        help="Comma-separated scenario IDs to run (default: all)"
    )
    parser.add_argument(
        "--trials", type=int, default=5,
        help="Number of trials per scenario (default: 5)"
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0,
        help="Timeout seconds per trial waiting for detection/mitigation (default: 60)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Return previously documented modelled values instead of live measurement"
    )
    parser.add_argument(
        "--output", default=os.path.join(_RESULTS_DIR, "live_benchmark_results.json"),
        help="Output JSON file path"
    )
    args = parser.parse_args()

    scenario_ids = [s.strip() for s in args.scenarios.split(",")]
    for sid in scenario_ids:
        if sid not in SCENARIO_REGISTRY:
            print(f"[!] Unknown scenario: {sid}. Valid: {list(SCENARIO_REGISTRY.keys())}")
            sys.exit(1)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    if args.dry_run:
        print("[*] Dry-run mode: returning MODELLED values (not live measurements).")
        results = run_dry_run(scenario_ids)
    else:
        results = []
        for sid in scenario_ids:
            r = run_live_scenario(
                sid, SCENARIO_REGISTRY[sid],
                n_trials=args.trials,
                timeout_sec=args.timeout
            )
            results.append(r)

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "MODELLED (dry-run)" if args.dry_run else "EMPIRICAL (live testbed)",
        "trials_per_scenario": args.trials,
        "scenarios": results
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\n[+] Results written to: {args.output}")


if __name__ == "__main__":
    main()
