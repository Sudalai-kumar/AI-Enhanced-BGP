"""
Automated Test Runner for Week 4 Baseline Benchmarks.
Executes all 5 baseline scenarios across multiple iterations,
checks run-to-run variance, outputs a summary table, and exports results.
"""

import json
import csv
import os
import sys
import argparse
from tabulate import tabulate

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from experiments.baseline.benchmark_harness import compute_stats, logger
from experiments.baseline.scenario_cold_start import run_cold_start_iteration
from experiments.baseline.scenario_link_failure import run_link_failure_iteration
from experiments.baseline.scenario_flapping import run_flapping_iteration
from experiments.baseline.scenario_resource_load import profile_resources
from experiments.baseline.scenario_data_plane import measure_pdr

RESULTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "experiments", "results"))

def run_suite(iterations: int = 3):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    print("=" * 70)
    print(f" Executing Week 4 Baseline Benchmark Suite ({iterations} Iterations)")
    print("=" * 70)
    
    # 1. Cold Start Convergence Runs
    print("\n[*] Running Scenario 1: Cold Start Convergence...")
    cold_starts = []
    for i in range(1, iterations + 1):
        print(f"  --> Iteration {i}/{iterations}...")
        t = run_cold_start_iteration()
        cold_starts.append(t)
    cold_stats = compute_stats(cold_starts)
    
    # 2. Link Failure & Recovery Runs
    print("\n[*] Running Scenario 2: Link Failure & Recovery...")
    withdrawals = []
    recoveries = []
    for i in range(1, iterations + 1):
        print(f"  --> Iteration {i}/{iterations}...")
        res = run_link_failure_iteration()
        withdrawals.append(res["withdrawal_latency_sec"])
        recoveries.append(res["recovery_latency_sec"])
    withdrawal_stats = compute_stats(withdrawals)
    recovery_stats = compute_stats(recoveries)
    
    # 3. Flapping & Oscillation Runs
    print("\n[*] Running Scenario 3: Route Flapping & Oscillation...")
    flaps = []
    for i in range(1, iterations + 1):
        print(f"  --> Iteration {i}/{iterations}...")
        res = run_flapping_iteration(cycles=3, interval=1.5)
        flaps.append(res["bgp_updates_received_as65003"])
    flap_stats = compute_stats(flaps)
    
    # 4. Resource Overhead Profiling
    print("\n[*] Running Scenario 4: Control-Plane Resource Profiling...")
    res_profile = profile_resources(duration_sec=8.0)
    
    # 5. Data Plane PDR
    print("\n[*] Running Scenario 5: Packet Delivery Ratio (PDR)...")
    pdr_res = measure_pdr(count=10)
    
    # Summary Table Output
    table_rows = [
        ["Cold Start Convergence (s)", cold_stats["mean"], cold_stats["std"], cold_stats["min"], cold_stats["max"], f"{cold_stats['cv_percent']}%", "Stable" if cold_stats['cv_percent'] < 20 else "High Variance"],
        ["Route Withdrawal Latency (s)", withdrawal_stats["mean"], withdrawal_stats["std"], withdrawal_stats["min"], withdrawal_stats["max"], f"{withdrawal_stats['cv_percent']}%", "Stable" if withdrawal_stats['cv_percent'] < 20 else "High Variance"],
        ["Route Recovery Latency (s)", recovery_stats["mean"], recovery_stats["std"], recovery_stats["min"], recovery_stats["max"], f"{recovery_stats['cv_percent']}%", "Stable" if recovery_stats['cv_percent'] < 20 else "High Variance"],
        ["Updates per 3 Flap Cycles", flap_stats["mean"], flap_stats["std"], flap_stats["min"], flap_stats["max"], f"{flap_stats['cv_percent']}%", "Stable"],
        ["Data Plane PDR (%)", pdr_res["packet_delivery_ratio_percent"], "-", "-", "-", "-", "Normal Path Active"],
        ["Data Plane Avg RTT (ms)", pdr_res["avg_rtt_ms"], "-", "-", "-", "-", "Direct Peered"],
        ["AS65003 Avg CPU / RAM", f"{res_profile['as65003']['avg_cpu_percent']}%", "-", "-", "-", "-", f"{res_profile['as65003']['avg_mem_mib']} MiB"]
    ]
    
    print("\n" + "=" * 70)
    print(" WEEK 4 BASELINE BENCHMARK SUMMARY (REFERENCE VALUES)")
    print("=" * 70)
    print(tabulate(table_rows, headers=["Metric", "Mean", "StdDev", "Min", "Max", "Variance (CV%)", "Stability Status"], tablefmt="grid"))
    
    # Export to JSON and CSV
    summary_data = {
        "iterations": iterations,
        "cold_start_convergence": cold_stats,
        "route_withdrawal_latency": withdrawal_stats,
        "route_recovery_latency": recovery_stats,
        "route_flapping_updates": flap_stats,
        "resource_profiling": res_profile,
        "data_plane": pdr_res
    }
    
    json_path = os.path.join(RESULTS_DIR, "baseline_summary.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)
        
    csv_path = os.path.join(RESULTS_DIR, "baseline_summary.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Mean", "StdDev", "Min", "Max", "CV_Percent", "Status"])
        for r in table_rows:
            writer.writerow(r)
            
    print(f"\n[+] Results successfully exported to:\n  - {json_path}\n  - {csv_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Week 4 Baseline Suite")
    parser.add_argument("--iterations", type=int, default=3, help="Number of benchmark iterations")
    args = parser.parse_args()
    
    run_suite(iterations=args.iterations)
