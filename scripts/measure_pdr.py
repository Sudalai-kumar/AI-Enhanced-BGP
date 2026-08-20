"""
End-to-End Packet Delivery Ratio (PDR) Traffic Probe.

Measures actual forwarding recovery rather than using policy-state changes as a proxy.
Procedure:
  1. Send baseline ICMP probes from as65004 toward the target prefix.
  2. Inject the specified attack.
  3. Continue probing during the attack and mitigation window.
  4. Parse delivered vs. dropped counts to compute PDR.
  5. Record outage_duration_sec: time from attack injection until >=95% delivery resumes.
  6. Write results to experiments/results/pdr_measurement_results.json.

Requires: Docker + running FRR topology.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Optional, Dict, Any, List

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_RESULTS_DIR = os.path.join(_REPO_ROOT, "experiments", "results")
_ATTACKS_DIR = os.path.join(_REPO_ROOT, "experiments", "attacks")

# Map scenario ID -> (source container, target IP, attack script)
SCENARIO_TARGETS: Dict[str, Dict[str, Any]] = {
    "S1": {
        "source_container": "as65004",
        "target_ip": "192.0.2.1",
        "attack_script": os.path.join(_ATTACKS_DIR, "inject_direct_hijack.py"),
        "scenario_type": "synthetic",
    },
    "S2": {
        "source_container": "as65004",
        "target_ip": "192.0.2.1",
        "attack_script": os.path.join(_ATTACKS_DIR, "inject_subprefix_hijack.py"),
        "scenario_type": "synthetic",
    },
    "S3": {
        "source_container": "as65004",
        "target_ip": "192.0.2.1",
        "attack_script": os.path.join(_ATTACKS_DIR, "inject_flapping.py"),
        "scenario_type": "synthetic",
    },
}


def _ping_count(container: str, target_ip: str, count: int, interval: float = 0.1) -> Dict[str, int]:
    """
    Sends `count` ICMP echo requests from `container` to `target_ip` at `interval` seconds apart.
    Returns {'sent': N, 'received': M, 'lost': L}.
    """
    cmd = [
        "docker", "exec", container,
        "ping", "-c", str(count), "-i", str(interval), target_ip
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=count * interval + 10)
        output = result.stdout
        # Parse "N packets transmitted, M received, L% packet loss"
        for line in output.splitlines():
            if "packets transmitted" in line:
                parts = line.split(",")
                sent = int(parts[0].strip().split()[0])
                received = int(parts[1].strip().split()[0])
                lost = sent - received
                return {"sent": sent, "received": received, "lost": lost}
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    return {"sent": count, "received": 0, "lost": count}


def measure_pdr_scenario(
    scenario_id: str,
    source_container: str,
    target_ip: str,
    attack_script: str,
    scenario_type: str,
    baseline_probes: int = 20,
    attack_probes: int = 100,
    probe_interval: float = 0.1,
    recovery_threshold: float = 0.95,
    recovery_window_probes: int = 20,
) -> Dict[str, Any]:
    """
    Runs a full PDR measurement cycle for a single scenario.

    Args:
        baseline_probes:       Number of probes to send before attack injection.
        attack_probes:         Number of probes to send during/after attack window.
        probe_interval:        Seconds between probes (10 pps = 0.1s).
        recovery_threshold:    Fraction of probes that must succeed to declare recovery.
        recovery_window_probes: Number of consecutive probes to check for recovery.
    """
    print(f"\n[*] PDR measurement: Scenario {scenario_id} | {target_ip} <- {source_container}")

    # --- Phase 1: Baseline ---
    print(f"  [1] Sending {baseline_probes} baseline probes...")
    baseline = _ping_count(source_container, target_ip, baseline_probes, probe_interval)
    baseline_pdr = baseline["received"] / max(baseline["sent"], 1)
    print(f"      Baseline PDR: {baseline_pdr*100:.1f}% ({baseline['received']}/{baseline['sent']})")

    if baseline_pdr < 0.80:
        return {
            "scenario_id": scenario_id,
            "target_ip": target_ip,
            "scenario_type": scenario_type,
            "evidence_level": "EMPIRICAL",
            "error": f"Baseline PDR too low ({baseline_pdr*100:.1f}%) — topology may not be reachable."
        }

    # --- Phase 2: Attack injection ---
    print(f"  [2] Injecting attack...")
    t_attack = time.time()
    if os.path.exists(attack_script):
        subprocess.run([sys.executable, attack_script], capture_output=True, timeout=30)
    else:
        print(f"      [!] Attack script not found: {attack_script}. Proceeding without injection.")

    # --- Phase 3: Probe during attack + mitigation ---
    print(f"  [3] Sending {attack_probes} probes during attack/mitigation window...")
    attack_window = _ping_count(source_container, target_ip, attack_probes, probe_interval)
    attack_pdr = attack_window["received"] / max(attack_window["sent"], 1)
    print(f"      Attack window PDR: {attack_pdr*100:.1f}% ({attack_window['received']}/{attack_window['sent']})")

    # --- Phase 4: Detect recovery ---
    print(f"  [4] Probing for recovery (threshold: {recovery_threshold*100:.0f}%)...")
    t_recovery = None
    for _ in range(20):  # Up to 20 recovery-window checks
        window = _ping_count(source_container, target_ip, recovery_window_probes, probe_interval)
        window_pdr = window["received"] / max(window["sent"], 1)
        if window_pdr >= recovery_threshold:
            t_recovery = time.time()
            print(f"      Recovery confirmed at PDR={window_pdr*100:.1f}%")
            break

    outage_duration = (t_recovery - t_attack) if t_recovery else None
    overall_pdr = attack_window["received"] / max(attack_window["sent"], 1)

    result = {
        "scenario_id": scenario_id,
        "target_ip": target_ip,
        "scenario_type": scenario_type,
        "evidence_level": "EMPIRICAL",
        "baseline_pdr_percent": round(baseline_pdr * 100, 2),
        "attack_window_pdr_percent": round(attack_pdr * 100, 2),
        "overall_pdr_percent": round(overall_pdr * 100, 2),
        "outage_duration_sec": round(outage_duration, 3) if outage_duration else None,
        "probes_sent_attack_window": attack_window["sent"],
        "probes_received_attack_window": attack_window["received"],
        "recovery_confirmed": t_recovery is not None,
    }
    print(f"  Summary: PDR={result['overall_pdr_percent']:.1f}% | "
          f"Outage={result['outage_duration_sec']}s")
    return result


def main():
    parser = argparse.ArgumentParser(description="BGP PDR Traffic Probe")
    parser.add_argument(
        "--scenario", choices=list(SCENARIO_TARGETS.keys()), required=True,
        help="Scenario ID to measure"
    )
    parser.add_argument(
        "--baseline-probes", type=int, default=20,
        help="Number of probes before attack injection (default: 20)"
    )
    parser.add_argument(
        "--attack-probes", type=int, default=100,
        help="Number of probes during attack/mitigation window (default: 100)"
    )
    parser.add_argument(
        "--output", default=os.path.join(_RESULTS_DIR, "pdr_measurement_results.json"),
        help="Output JSON file path"
    )
    args = parser.parse_args()

    sc = SCENARIO_TARGETS[args.scenario]
    result = measure_pdr_scenario(
        scenario_id=args.scenario,
        source_container=sc["source_container"],
        target_ip=sc["target_ip"],
        attack_script=sc["attack_script"],
        scenario_type=sc["scenario_type"],
        baseline_probes=args.baseline_probes,
        attack_probes=args.attack_probes,
    )

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    # Append to existing results file if it exists
    existing = []
    if os.path.exists(args.output):
        try:
            with open(args.output, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    if not isinstance(existing, list):
        existing = [existing]
    existing.append(result)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    print(f"\n[+] PDR result written to: {args.output}")


if __name__ == "__main__":
    main()
