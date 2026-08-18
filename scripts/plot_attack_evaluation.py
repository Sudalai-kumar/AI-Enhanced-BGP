"""
Publication-Quality Comparative Visualizations for Attack Benchmarks.
Generates:
1. Data Plane Packet Delivery Ratio (PDR) Preservation under Attacks (S1-S6).
2. Mitigation Latency (MTTM) across Configurations.
3. Multi-Metric Benchmark Comparison Radar/Grouped Bar Plot.
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
    json_path = os.path.join(RESULTS_DIR, "attack_evaluation_results.json")
    
    if not os.path.exists(json_path):
        print(f"[!] Results JSON not found at {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    labels = [s["scenario_id"] for s in scenarios]
    scenario_titles = [s["scenario_name"] for s in scenarios]
    
    # -------------------------------------------------------------------------
    # Plot 1: Packet Delivery Ratio (PDR) Preservation
    # -------------------------------------------------------------------------
    pdr_std = [s["standard_bgp"]["pdr_percent"] for s in scenarios]
    pdr_rpki = [s["rpki_rov"]["pdr_percent"] for s in scenarios]
    pdr_heur = [s["heuristics"]["pdr_percent"] for s in scenarios]
    pdr_ai = [s["proposed_ai"]["pdr_percent"] for s in scenarios]

    x = np.arange(len(labels))
    width = 0.20

    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    fig, ax = plt.subplots(figsize=(11, 5.5))
    
    r1 = ax.bar(x - 1.5*width, pdr_std, width, label="Standard BGP (RFC)", color="#e74c3c", alpha=0.90)
    r2 = ax.bar(x - 0.5*width, pdr_rpki, width, label="BGP + RPKI ROV (RFC 6811)", color="#f39c12", alpha=0.90)
    r3 = ax.bar(x + 0.5*width, pdr_heur, width, label="Behavioural Heuristics", color="#3498db", alpha=0.90)
    r4 = ax.bar(x + 1.5*width, pdr_ai, width, label="Proposed AI Control Plane (Live)", color="#27ae60", alpha=0.95)

    ax.set_ylabel("Packet Delivery Ratio (%)", fontsize=11, fontweight="bold")
    ax.set_title("Data Plane PDR Preservation Under BGP Routing Attacks (Scenarios S1–S6)", fontsize=13, fontweight="bold", pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{s['scenario_id']}\n{s['scenario_name'][:18]}..." if len(s['scenario_name']) > 18 else f"{s['scenario_id']}\n{s['scenario_name']}" for s in scenarios], fontsize=9, fontweight="bold")
    ax.set_ylim(0, 115)
    ax.legend(loc="upper left", frameon=True, shadow=True, fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    plot1_path = os.path.join(FIGURES_DIR, "comparative_pdr_evaluation.png")
    plt.savefig(plot1_path, dpi=300)
    plt.close()

    # -------------------------------------------------------------------------
    # Plot 2: Mean Time to Mitigate (MTTM) Comparison
    # -------------------------------------------------------------------------
    fig, ax2 = plt.subplots(figsize=(10, 5.5))
    mttm_std = [9.04] * len(scenarios)
    mttm_heur = [s["heuristics"]["mttm_sec"] for s in scenarios]
    mttm_ai = [s["proposed_ai"]["mttm_sec"] for s in scenarios]

    x2 = np.arange(len(labels))
    w2 = 0.35

    ax2.bar(x2 - 0.5*w2, mttm_heur, w2, label="Behavioural Heuristics MTTM", color="#3498db", alpha=0.85)
    ax2.bar(x2 + 0.5*w2, mttm_ai, w2, label="Proposed AI Control Plane MTTM", color="#27ae60", alpha=0.95)
    ax2.plot(x2, mttm_std, "r--o", label="Native BGP Hold-Timer (~9.04s baseline)", linewidth=2.2, markersize=7)

    ax2.set_ylabel("Mitigation Latency (Seconds)", fontsize=11, fontweight="bold")
    ax2.set_title("Autonomous Mitigation Latency (MTTM): Heuristics vs Proposed AI Control Plane", fontsize=13, fontweight="bold", pad=12)
    ax2.set_xticks(x2)
    ax2.set_xticklabels(labels, fontweight="bold", fontsize=10)
    ax2.legend(loc="upper left", frameon=True, shadow=True, fontsize=10)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)

    for i, v in enumerate(mttm_ai):
        ax2.text(i + 0.5*w2, v + 0.3, f"{v:.2f}s", ha="center", fontweight="bold", fontsize=9, color="#1e824c")

    plt.tight_layout()
    plot2_path = os.path.join(FIGURES_DIR, "comparative_mttm_latency.png")
    plt.savefig(plot2_path, dpi=300)
    plt.close()

    print(f"[+] High-resolution comparative figures regenerated:\n  - {plot1_path}\n  - {plot2_path}")

if __name__ == "__main__":
    generate_plots()
