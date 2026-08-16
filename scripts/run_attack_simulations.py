"""
Master CLI Runner for Week 8 Attack Simulations and Comparative Evaluation.
Runs all 6 scenarios across Standard BGP, RPKI ROV, Heuristics, and AI Control Plane.
"""

import sys
import os
import argparse
from tabulate import tabulate

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from experiments.comparative.benchmark_evaluator import ComparativeEvaluator

def main():
    parser = argparse.ArgumentParser(description="Week 8 Attack Evaluation Runner")
    parser.add_argument("--iterations", type=int, default=3, help="Benchmark iterations")
    args = parser.parse_args()

    evaluator = ComparativeEvaluator()
    results = evaluator.run_all_benchmarks()

    print("\n" + "=" * 95)
    print(" WEEK 8 ATTACK SIMULATION & 4-WAY COMPARATIVE EVALUATION MATRIX")
    print("=" * 95)
    
    table_rows = []
    for sc in results:
        s_id = sc["scenario_id"]
        s_name = sc["scenario_name"]
        
        c1 = sc["standard_bgp"]
        c2 = sc["rpki_rov"]
        c3 = sc["heuristics"]
        c4 = sc["proposed_ai"]
        
        table_rows.append([
            f"{s_id}: {s_name}",
            "Standard BGP",
            "No" if not c1["detected"] else "Yes",
            "-",
            f"{c1['mttm_sec']}s",
            f"{c1['pdr_percent']}%",
            c1["action"]
        ])
        table_rows.append([
            "",
            "BGP + RPKI ROV",
            "Yes" if c2["detected"] else "No (Out of Scope)" if "Out of Scope" in str(c2.get("action")) else "No",
            f"{c2['mttd_sec']}s" if c2['mttd_sec'] else "-",
            f"{c2['mttm_sec']}s" if c2['mttm_sec'] else "-",
            f"{c2['pdr_percent']}%",
            c2["action"]
        ])
        table_rows.append([
            "",
            "Behavioural Heuristics",
            "Yes" if c3["detected"] else "No",
            f"{c3['mttd_sec']}s",
            f"{c3['mttm_sec']}s",
            f"{c3['pdr_percent']}%",
            c3["action"]
        ])
        table_rows.append([
            "",
            "Proposed AI Control Plane",
            "Yes" if c4["detected"] else "No",
            f"{c4['mttd_sec']}s",
            f"{c4['mttm_sec']}s",
            f"{c4['pdr_percent']}%",
            c4["action"]
        ])
        table_rows.append(["-" * 30, "-" * 20, "-" * 8, "-" * 8, "-" * 8, "-" * 10, "-" * 25])

    print(tabulate(
        table_rows,
        headers=["Scenario", "Configuration", "Detected?", "MTTD", "MTTM", "PDR (%)", "Applied Mitigation Action"],
        tablefmt="grid"
    ))

if __name__ == "__main__":
    main()
