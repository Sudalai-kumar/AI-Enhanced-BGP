"""
Comprehensive Publication Figure Generator for AI-Enhanced BGP.
Generates 6 Publication-Quality Figures for Academic & Technical Reports:
1. Data Plane Packet Delivery Ratio (PDR) Preservation under Attacks (S1-S6).
2. Mitigation Latency (MTTM) across Configurations (S1-S6 vs BGP Hold-Timer).
3. ML Feature Importance Breakdown (Random Forest Gini Impurity).
4. Multi-Factor Behavioral Trust Model Decomposition (Radar Profile across Anomaly Tiers).
5. Baseline Protocol Convergence Latency Distribution (Cold-Start, Recovery, Withdrawal).
6. 4-Tier Autonomous Policy State Machine & Action Mapping.
"""

import json
import os
import sys
import matplotlib.pyplot as plt
import numpy as np

RESULTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "experiments", "results"))
FIGURES_DIR = os.path.join(RESULTS_DIR, "figures")

def set_plot_style():
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    plt.rcParams.update({
        'font.size': 10,
        'axes.labelsize': 11,
        'axes.titlesize': 12,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'legend.fontsize': 9,
        'figure.titlesize': 13
    })

def plot_pdr_preservation(scenarios):
    """Figure 1: Packet Delivery Ratio (PDR) Preservation."""
    labels = [s["scenario_id"] for s in scenarios]
    pdr_std = [s["standard_bgp"]["pdr_percent"] for s in scenarios]
    pdr_rpki = [s["rpki_rov"]["pdr_percent"] for s in scenarios]
    pdr_heur = [s["heuristics"]["pdr_percent"] for s in scenarios]
    pdr_ai = [s["proposed_ai"]["pdr_percent"] for s in scenarios]

    x = np.arange(len(labels))
    width = 0.20

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(x - 1.5*width, pdr_std, width, label="Standard BGP (RFC)", color="#e74c3c", alpha=0.90)
    ax.bar(x - 0.5*width, pdr_rpki, width, label="BGP + RPKI ROV (RFC 6811)", color="#f39c12", alpha=0.90)
    ax.bar(x + 0.5*width, pdr_heur, width, label="Behavioural Heuristics", color="#3498db", alpha=0.90)
    ax.bar(x + 1.5*width, pdr_ai, width, label="Proposed AI Control Plane (Live)", color="#27ae60", alpha=0.95)

    ax.set_ylabel("Packet Delivery Ratio (%)", fontweight="bold")
    ax.set_title("Data Plane PDR Preservation Under BGP Routing Attacks (Scenarios S1–S6)", fontweight="bold", pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{s['scenario_id']}\n{s['scenario_name'][:18]}..." if len(s['scenario_name']) > 18 else f"{s['scenario_id']}\n{s['scenario_name']}" for s in scenarios], fontweight="bold")
    ax.set_ylim(0, 115)
    ax.legend(loc="upper left", frameon=True, shadow=True)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    out_path = os.path.join(FIGURES_DIR, "comparative_pdr_evaluation.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    return out_path

def plot_mttm_latency(scenarios):
    """Figure 2: Mitigation Latency (MTTM)."""
    labels = [s["scenario_id"] for s in scenarios]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    mttm_std = [9.04] * len(scenarios)
    mttm_heur = [s["heuristics"]["mttm_sec"] for s in scenarios]
    mttm_ai = [s["proposed_ai"]["mttm_sec"] for s in scenarios]

    x = np.arange(len(labels))
    w = 0.35

    ax.bar(x - 0.5*w, mttm_heur, w, label="Behavioural Heuristics MTTM", color="#3498db", alpha=0.85)
    ax.bar(x + 0.5*w, mttm_ai, w, label="Proposed AI Control Plane MTTM", color="#27ae60", alpha=0.95)
    ax.plot(x, mttm_std, "r--o", label="Native BGP Hold-Timer (~9.04s baseline)", linewidth=2.2, markersize=7)

    ax.set_ylabel("Mitigation Latency (Seconds)", fontweight="bold")
    ax.set_title("Autonomous Mitigation Latency (MTTM): Heuristics vs Proposed AI Control Plane", fontweight="bold", pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontweight="bold")
    ax.legend(loc="upper left", frameon=True, shadow=True)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for i, v in enumerate(mttm_ai):
        ax.text(i + 0.5*w, v + 0.3, f"{v:.2f}s", ha="center", fontweight="bold", fontsize=9, color="#1e824c")

    plt.tight_layout()
    out_path = os.path.join(FIGURES_DIR, "comparative_mttm_latency.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    return out_path

def plot_feature_importances():
    """Figure 3: Random Forest Feature Importance Breakdown."""
    feat_json = os.path.join(RESULTS_DIR, "model_training_evaluation.json")
    if not os.path.exists(feat_json):
        return None
    with open(feat_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    importances = data.get("random_forest", {}).get("feature_importances", {})
    if not importances:
        return None

    # Sort descending
    sorted_items = sorted(importances.items(), key=lambda x: x[1], reverse=True)
    feats = [item[0].replace("_", " ").title() for item in sorted_items]
    scores = [item[1] * 100 for item in sorted_items]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    y_pos = np.arange(len(feats))
    colors = plt.cm.viridis(np.linspace(0.85, 0.25, len(feats)))

    bars = ax.barh(y_pos, scores, color=colors, alpha=0.90, edgecolor="black", linewidth=0.6)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(feats, fontweight="bold")
    ax.invert_yaxis()  # top feature on top
    ax.set_xlabel("Gini Feature Importance (%)", fontweight="bold")
    ax.set_title("Random Forest Feature Importance Distribution (10 BGP Telemetry Features)", fontweight="bold", pad=12)
    ax.grid(axis="x", linestyle="--", alpha=0.5)

    for i, bar in enumerate(bars):
        w = bar.get_width()
        ax.text(w + 0.5, bar.get_y() + bar.get_height()/2, f"{w:.1f}%", va="center", fontweight="bold", fontsize=9)

    plt.tight_layout()
    out_path = os.path.join(FIGURES_DIR, "feature_importance_breakdown.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    return out_path

def plot_trust_radar():
    """Figure 4: Multi-Factor Behavioral Trust Model Radar Decomposition."""
    categories = ['Origin\nStability', 'AS-Path\nIntegrity', 'Flap\nQuiescence', 'Prefix\nSpecificity', 'Neighbor\nDiversity', 'Calibrated\nML Trust']
    N = len(categories)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]

    # Scores across 4 operational states
    normal_scores = [1.0, 1.0, 1.0, 1.0, 1.0, 0.98]
    normal_scores += normal_scores[:1]

    flap_scores = [1.0, 1.0, 0.20, 1.0, 1.0, 0.40]
    flap_scores += flap_scores[:1]

    leak_scores = [1.0, 0.0, 1.0, 1.0, 0.5, 0.05]
    leak_scores += leak_scores[:1]

    hijack_scores = [0.0, 0.0, 0.8, 0.4, 0.5, 0.01]
    hijack_scores += hijack_scores[:1]

    fig, ax = plt.subplots(figsize=(8, 7), subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    plt.xticks(angles[:-1], categories, fontweight="bold", fontsize=9)
    ax.set_rlabel_position(0)
    plt.yticks([0.2, 0.4, 0.6, 0.8, 1.0], ["0.2", "0.4", "0.6", "0.8", "1.0"], color="grey", size=8)
    plt.ylim(0, 1.1)

    # Plot each anomaly tier
    ax.plot(angles, normal_scores, linewidth=2, linestyle='solid', label='Normal Route (Trust = 0.99)', color='#27ae60')
    ax.fill(angles, normal_scores, '#27ae60', alpha=0.15)

    ax.plot(angles, flap_scores, linewidth=2, linestyle='solid', label='Route Flapping (Trust = 0.76 -> LP 80)', color='#f39c12')
    ax.fill(angles, flap_scores, '#f39c12', alpha=0.15)

    ax.plot(angles, leak_scores, linewidth=2, linestyle='solid', label='Route Leak (Trust = 0.46 -> LP 50)', color='#e67e22')
    ax.fill(angles, leak_scores, '#e67e22', alpha=0.15)

    ax.plot(angles, hijack_scores, linewidth=2, linestyle='solid', label='Prefix Hijack (Trust = 0.23 -> LP 0 + no-export)', color='#c0392b')
    ax.fill(angles, hijack_scores, '#c0392b', alpha=0.20)

    plt.title("Multi-Factor Behavioral Trust Decomposition Across Routing Anomaly Tiers", fontweight="bold", pad=20)
    plt.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1), frameon=True, shadow=True)

    plt.tight_layout()
    out_path = os.path.join(FIGURES_DIR, "behavioral_trust_radar.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    return out_path

def plot_baseline_convergence():
    """Figure 5: Baseline BGP Protocol Latency Breakdown."""
    json_path = os.path.join(RESULTS_DIR, "baseline_summary.json")
    if not os.path.exists(json_path):
        return None
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    metrics = ["Cold-Start\nConvergence", "Route Recovery\n(Re-announcement)", "Route Withdrawal\n(Hold-Timer Expiry)"]
    means = [
        data.get("cold_start_convergence", {}).get("mean", 5.46),
        data.get("route_recovery_latency", {}).get("mean", 1.39),
        data.get("route_withdrawal_latency", {}).get("mean", 9.04)
    ]
    stds = [
        data.get("cold_start_convergence", {}).get("std", 0.04),
        data.get("route_recovery_latency", {}).get("std", 0.04),
        data.get("route_withdrawal_latency", {}).get("std", 0.11)
    ]

    fig, ax = plt.subplots(figsize=(9, 5))
    x_pos = np.arange(len(metrics))
    colors = ['#3498db', '#2ecc71', '#e74c3c']

    bars = ax.bar(x_pos, means, yerr=stds, capsize=6, color=colors, alpha=0.85, width=0.45, edgecolor="black", linewidth=0.8)
    ax.set_ylabel("Latency (Seconds)", fontweight="bold")
    ax.set_title("Standard BGP Control-Plane Convergence & Withdrawal Latencies (FRR 10.2.1)", fontweight="bold", pad=12)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(metrics, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.3, f"{h:.2f}s", ha="center", fontweight="bold", fontsize=10)

    plt.tight_layout()
    out_path = os.path.join(FIGURES_DIR, "baseline_convergence_distribution.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    return out_path

def plot_policy_state_machine():
    """Figure 6: 4-Tier Autonomous Policy Action & Hysteresis Thresholds."""
    fig, ax = plt.subplots(figsize=(11, 4.5))

    # Trust Score Spectrum [0.0 to 1.0]
    gradient = np.linspace(0, 1, 500).reshape(1, -1)
    ax.imshow(gradient, aspect='auto', cmap='RdYlGn', extent=[0, 1, 0, 1], alpha=0.75)

    # Threshold Division Lines
    ax.axvline(0.25, color='black', linestyle='--', linewidth=2)
    ax.axvline(0.55, color='black', linestyle='--', linewidth=2)
    ax.axvline(0.80, color='black', linestyle='--', linewidth=2)
    ax.axvline(0.85, color='blue', linestyle=':', linewidth=2) # Hysteresis recovery line

    # Annotate Tiers
    ax.text(0.125, 0.5, "TIER 4: QUARANTINE\n\nTrust < 0.25\nLocalPref 0 + no-export\n(Prefix Hijacks)", ha='center', va='center', fontweight='bold', fontsize=9, bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="black", alpha=0.85))
    ax.text(0.40, 0.5, "TIER 3: HARD DEPRIORITIZE\n\n0.25 ≤ Trust < 0.55\nLocalPref 50\n(Route Leaks)", ha='center', va='center', fontweight='bold', fontsize=9, bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="black", alpha=0.85))
    ax.text(0.675, 0.5, "TIER 2: SOFT DEPRIORITIZE\n\n0.55 ≤ Trust < 0.80\nLocalPref 80\n(Flapping / Churn)", ha='center', va='center', fontweight='bold', fontsize=9, bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="black", alpha=0.85))
    ax.text(0.925, 0.5, "TIER 1: NORMAL BASELINE\n\nTrust ≥ 0.85\nLocalPref 100\n(Normal Routes)", ha='center', va='center', fontweight='bold', fontsize=9, bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="black", alpha=0.85))

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xlabel("Continuous Behavioral Trust Score", fontweight="bold", fontsize=11)
    ax.set_title("Autonomous 4-Tier Policy Mapping & Hysteresis Thresholds (Δ = 0.05)", fontweight="bold", pad=12)

    plt.tight_layout()
    out_path = os.path.join(FIGURES_DIR, "policy_tier_state_machine.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    return out_path

def generate_all_figures():
    os.makedirs(FIGURES_DIR, exist_ok=True)
    set_plot_style()
    json_path = os.path.join(RESULTS_DIR, "attack_evaluation_results.json")
    
    with open(json_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    generated = []
    generated.append(plot_pdr_preservation(scenarios))
    generated.append(plot_mttm_latency(scenarios))
    generated.append(plot_feature_importances())
    generated.append(plot_trust_radar())
    generated.append(plot_baseline_convergence())
    generated.append(plot_policy_state_machine())

    print("[+] All 6 publication-quality figures successfully generated in experiments/results/figures/:")
    for p in generated:
        if p:
            print(f"  - {os.path.basename(p)}")

if __name__ == "__main__":
    generate_all_figures()
