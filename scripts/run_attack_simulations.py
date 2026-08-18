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

    print("\n" + "=" * 115)
    print(" WEEK 8 ATTACK SIMULATION & 4-WAY COMPARATIVE EVALUATION MATRIX")
    print("=" * 115)
    
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
            "Standard BGP (RFC)",
            "No" if not c1["detected"] else "Yes",
            c1["mttd_sec"],
            c1["mttm_sec"],
            f"{c1['pdr_percent']}%",
            f"{c1.get('f1', 'N/A')}",
            c1["action"]
        ])
        table_rows.append([
            "",
            "BGP + RPKI ROV (RFC 6811)",
            "Yes" if c2["detected"] else "No (Out of Scope)" if "Out of Scope" in str(c2.get("action")) else "No",
            c2["mttd_sec"],
            c2["mttm_sec"],
            f"{c2['pdr_percent']}%",
            f"{c2.get('f1', 'N/A')}",
            c2["action"]
        ])
        table_rows.append([
            "",
            "Behavioural Heuristics",
            "Yes" if c3["detected"] else "No",
            f"{c3['mttd_sec']}s" if isinstance(c3['mttd_sec'], (int, float)) else str(c3['mttd_sec']),
            f"{c3['mttm_sec']}s" if isinstance(c3['mttm_sec'], (int, float)) else str(c3['mttm_sec']),
            f"{c3['pdr_percent']}%",
            f"{c3.get('f1', 'N/A')}",
            c3["action"]
        ])
        table_rows.append([
            "",
            "Proposed AI Control Plane (Live)",
            "Yes" if c4["detected"] else "No (Censored)",
            f"{c4['mttd_sec']}" + (f" (±{c4['mttd_std']})" if c4.get('mttd_std') is not None else ""),
            f"{c4['mttm_sec']}" + (f" (±{c4['mttm_std']})" if c4.get('mttm_std') is not None else ""),
            f"{c4['pdr_percent']}%",
            f"{c4.get('f1', 'N/A')}",
            c4["action"]
        ])
        table_rows.append(["-" * 28, "-" * 28, "-" * 12, "-" * 16, "-" * 16, "-" * 8, "-" * 8, "-" * 26])

    print(tabulate(
        table_rows,
        headers=["Scenario", "Configuration", "Detected?", "MTTD", "MTTM", "PDR", "F1", "Applied Mitigation Action"],
        tablefmt="grid"
    ))

if __name__ == "__main__":
    main()
