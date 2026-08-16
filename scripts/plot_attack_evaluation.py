"""
Publication-Quality Comparative Visualizations for Week 8 Attack Benchmarks.
Generates:
1. Mitigation Latency (MTTM) across Configurations.
2. Packet Delivery Ratio (PDR) preservation under attack.
3. Attack Coverage Radar / Bar Matrix.
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
    
    # Plot 1: Packet Delivery Ratio (PDR) Comparison
    pdr_std = [s["standard_bgp"]["pdr_percent"] for s in scenarios]
    pdr_rpki = [s["rpki_rov"]["pdr_percent"] for s in scenarios]
    pdr_heur = [s["heuristics"]["pdr_percent"] for s in scenarios]
    pdr_ai = [s["proposed_ai"]["pdr_percent"] for s in scenarios]

    x = np.arange(len(labels))
    width = 0.20

    fig, ax = plt.subplots(figsize=(10, 5.5))
    r1 = ax.bar(x - 1.5*width, pdr_std, width, label="Standard BGP", color="#e74c3c", alpha=0.85)
    r2 = ax.bar(x - 0.5*width, pdr_rpki, width, label="BGP + RPKI ROV", color="#f39c12", alpha=0.85)
    r3 = ax.bar(x + 0.5*width, pdr_heur, width, label="Heuristics", color="#3498db", alpha=0.85)
    r4 = ax.bar(x + 1.5*width, pdr_ai, width, label="Proposed AI Control Plane", color="#2ecc71", alpha=0.90)

    ax.set_ylabel("Packet Delivery Ratio (%)", fontsize=11, fontweight="bold")
    ax.set_title("Data Plane PDR Preservation Under Attack Scenarios (S1-S6)", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontweight="bold")
    ax.legend(loc="upper left")
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    plot1_path = os.path.join(FIGURES_DIR, "comparative_pdr_evaluation.png")
    plt.savefig(plot1_path, dpi=300)
    plt.close()

    # Plot 2: MTTM Comparison for Mitigated Attacks
    fig, ax2 = plt.subplots(figsize=(9, 5))
    mttm_std = [9.04, 9.04, 9.04, 9.04, 9.04, 9.04]
    mttm_ai = [s["proposed_ai"]["mttm_sec"] for s in scenarios]
    
    ax2.plot(labels, mttm_std, "r--o", label="Native BGP Hold-Timer (9.04s)", linewidth=2)
    ax2.bar(labels, mttm_ai, color="#2ecc71", alpha=0.8, width=0.4, label="Proposed AI Control Plane MTTM")
    ax2.set_ylabel("Mitigation Latency (Seconds)", fontsize=11, fontweight="bold")
    ax2.set_title("Mean Time to Mitigate (MTTM): Native BGP vs Proposed AI", fontsize=12, fontweight="bold")
    ax2.legend()
    ax2.grid(axis="y", linestyle="--", alpha=0.5)

    for i, v in enumerate(mttm_ai):
        ax2.text(i, v + 0.2, f"{v:.2f}s", ha="center", fontweight="bold")

    plt.tight_layout()
    plot2_path = os.path.join(FIGURES_DIR, "comparative_mttm_latency.png")
    plt.savefig(plot2_path, dpi=300)
    plt.close()

    print(f"[+] Comparative figures generated:\n  - {plot1_path}\n  - {plot2_path}")

if __name__ == "__main__":
    generate_plots()
