"""
Master CLI Runner for Week 8 Attack Simulations and 4-Way Comparative Evaluation.
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
    results = evaluator.run_all_benchmarks(iterations=args.iterations)

    print("\n" + "=" * 105)
    print(" WEEK 8 ATTACK SIMULATION & 4-WAY COMPARATIVE EVALUATION MATRIX (LIVE MEASURED)")
    print("=" * 105)
    
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
            f"{c1.get('f1', 'N/A')}",
            c1["action"]
        ])
        table_rows.append([
            "",
            "BGP + RPKI ROV",
            "Yes" if c2["detected"] else "No (Out of Scope)" if "Out of Scope" in str(c2.get("action")) else "No",
            f"{c2['mttd_sec']}s" if c2['mttd_sec'] else "-",
            f"{c2['mttm_sec']}s" if c2['mttm_sec'] else "-",
            f"{c2['pdr_percent']}%",
            f"{c2.get('f1', 'N/A')}",
            c2["action"]
        ])
        table_rows.append([
            "",
            "Behavioural Heuristics",
            "Yes" if c3["detected"] else "No",
            f"{c3['mttd_sec']}s",
            f"{c3['mttm_sec']}s",
            f"{c3['pdr_percent']}%",
            f"{c3.get('f1', 'N/A')}",
            c3["action"]
        ])
        table_rows.append([
            "",
            "Proposed AI Control Plane",
            "Yes" if c4["detected"] else "No",
            f"{c4['mttd_sec']}s (±{c4['mttd_std']})",
            f"{c4['mttm_sec']}s (±{c4['mttm_std']})",
            f"{c4['pdr_percent']}%",
            f"{c4.get('f1', 'N/A')}",
            c4["action"]
        ])
        table_rows.append(["-" * 28, "-" * 22, "-" * 8, "-" * 14, "-" * 14, "-" * 8, "-" * 8, "-" * 26])

    print(tabulate(
        table_rows,
        headers=["Scenario", "Configuration", "Detected?", "MTTD (Mean)", "MTTM (Mean)", "PDR", "F1", "Applied Mitigation Action"],
        tablefmt="grid"
    ))

if __name__ == "__main__":
    main()
