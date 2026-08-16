"""
Visualization generator for Week 4 Baseline Experiments.
Generates charts for:
1. Convergence Latency Breakdown.
2. Control-Plane Memory & CPU Utilization per Autonomous System.
3. Packet Delivery Ratio & Stability.
"""

import json
import os
import sys
import matplotlib.pyplot as plt
import numpy as np

RESULTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "experiments", "results"))
FIGURES_DIR = os.path.join(RESULTS_DIR, "figures")

def generate_plots():
    os.makedirs(FIGURES_DIR, exist_ok=True)
    json_path = os.path.join(RESULTS_DIR, "baseline_summary.json")
    
    if not os.path.exists(json_path):
        print(f"[!] JSON results not found at {json_path}. Run run_baseline_benchmarks.py first.")
        return
        
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # Plot 1: Convergence Latencies
    metrics = ["Cold Start", "Route Withdrawal", "Route Recovery"]
    means = [
        data["cold_start_convergence"]["mean"],
        data["route_withdrawal_latency"]["mean"],
        data["route_recovery_latency"]["mean"]
    ]
    stds = [
        data["cold_start_convergence"]["std"],
        data["route_withdrawal_latency"]["std"],
        data["route_recovery_latency"]["std"]
    ]
    
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(metrics, means, yerr=stds, capsize=6, color=["#2b5c8f", "#d9534f", "#5cb85c"], alpha=0.85, edgecolor="black")
    ax.set_ylabel("Latency (Seconds)", fontsize=11, fontweight="bold")
    ax.set_title("Baseline BGP Control-Plane Latency Metrics (Unmodified FRR)", fontsize=12, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f"{height:.2f}s",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontweight="bold")
                    
    plt.tight_layout()
    plot1_path = os.path.join(FIGURES_DIR, "baseline_latencies.png")
    plt.savefig(plot1_path, dpi=300)
    plt.close()
    
    # Plot 2: Memory Footprint per Node
    nodes = list(data["resource_profiling"].keys())
    mems = [data["resource_profiling"][n]["avg_mem_mib"] for n in nodes]
    
    fig, ax = plt.subplots(figsize=(8, 5))
    bars2 = ax.bar([n.upper() for n in nodes], mems, color="#4a90e2", alpha=0.85, edgecolor="black")
    ax.set_ylabel("Memory Footprint (MiB RSS)", fontsize=11, fontweight="bold")
    ax.set_title("FRRouting Baseline Memory Overhead per AS Node", fontsize=12, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    
    for bar in bars2:
        height = bar.get_height()
        ax.annotate(f"{height:.1f} MiB",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontweight="bold")
                    
    plt.tight_layout()
    plot2_path = os.path.join(FIGURES_DIR, "baseline_memory.png")
    plt.savefig(plot2_path, dpi=300)
    plt.close()
    
    print(f"[+] Baseline visualization figures generated at:\n  - {plot1_path}\n  - {plot2_path}")

if __name__ == "__main__":
    generate_plots()
