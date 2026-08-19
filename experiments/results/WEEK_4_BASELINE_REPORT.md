# Technical Milestone Report: Week 4 - Baseline Experiments

**Project Title:** An AI-Enhanced BGP Control Plane Architecture for Behavioral Route Leak and Hijack Mitigation  
**Milestone:** Month 1, Week 4 (Baseline Experiments & Performance Profiling)  
**Date:** 2026-08-16 (Verified 2026-08-19)  
**Environment:** Containerized FRRouting (FRR 10.2.1) with Point-to-Point Topology Emulation  

---

## 1. Executive Summary

During Week 4, we established empirical, reproducible reference baselines on an unmodified, standards-compliant BGP control plane. The goal of this milestone was to quantify the native behavior of BGP without AI intervention across:
1. Multi-AS Convergence Latency (Cold Start, Link Drop Withdrawal, Re-convergence)
2. Route Oscillation & BGP UPDATE message churn during link flapping
3. Data Plane Reachability & Packet Delivery Ratio (PDR)
4. Baseline Control-Plane Resource Overhead (CPU % and Memory RSS)
5. Run-to-Run Variance Verification across repeated trials

These quantitative baselines serve as the ground-truth control group against which the AI-enhanced control plane (developed in Months 2 & 3) will be evaluated.

---

## 2. Review of Implementation Plan Refinements & User Feedback

All feedback and suggestions provided on the implementation plan were integrated:

| User Suggestion / Risk | Status | Implementation Detail |
|---|---|---|
| **Subnet Alignment (`net_12: 10.0.12.0/29`)** | **Resolved** | Updated both Containerlab and Docker Compose topologies, router configurations, and test scripts to use `10.0.12.0/29` with exact IP allocations (`10.0.12.2` and `10.0.12.3`), preventing any failure-injection target mismatch. |
| **Run-to-Run Variance Verification** | **Implemented** | Added automated statistical variance checks in [`benchmark_harness.py`](file:///c:/Users/pebu/OneDrive/Documents/sem%205/NDC%20project/experiments/baseline/benchmark_harness.py) calculating the Coefficient of Variation ($CV\%$). All convergence metrics exhibited $CV < 3\%$, confirming high stability. |
| **Resource Overhead Methodology Reusability** | **Designed** | Implemented standardized process-level container sampling in [`scenario_resource_load.py`](file:///c:/Users/pebu/OneDrive/Documents/sem%205/NDC%20project/experiments/baseline/scenario_resource_load.py) that will be directly reused in Weeks 5–6 for the Python AI agent to ensure an exact apples-to-apples comparison. |
| **MTTD / MTTM Clarification & Framing** | **Framed** | Documented that native BGP baseline recovery times reflect standard BGP Hold-Timer / keepalive expirations (naive protocol-level response), establishing the unmitigated benchmark before introducing behavioral AI detection. |

---

## 3. Experimental Topology & Testbed

```
             +-----------------------+
             |       AS 65002        |
             |   Transit ISP (FRR)   |
             +-----------+-----------+
                        / \
    net_12: 10.0.12.0/29 \   / net_23: 10.0.23.0/29
   (10.0.12.2 <-> 10.0.12.3) (10.0.23.2 <-> 10.0.23.3)
                      /     \
  +------------------+       +-------------------+
  |     AS 65001     |       |     AS 65003      |
  |  Origin / Victim |       | Receiver / Monitor|
  |  192.0.2.0/24    |       | (FRR 10.2.1)      |
  |  198.51.100.0/24 |       +---------+---------+
  +------------------+                 | net_34: 10.0.34.0/29
                                       | (10.0.34.2 <-> 10.0.34.3)
                             +---------+---------+
                             |     AS 65004      |
                             | Attacker (W8 Idle)|
                             +-------------------+
```

- **FRRouting Version**: `quay.io/frrouting/frr:10.2.1` (pinned across all manifests)
- **Routing Protocol**: BGP-4 / IPv4 Unicast with eBGP peering
- **Timers**: BGP Keepalive = 3s, Hold Time = 9s

---

## 4. Quantitative Results & Metrics Summary

Each benchmark was executed across **3 independent automated trials**.

```
+------------------------------+--------+----------+--------+--------+------------------+--------------------+
| Metric                       | Mean   | StdDev   | Min    | Max    | Variance (CV%)   | Stability Status   |
+==============================+========+==========+========+========+==================+====================+
| Cold Start Convergence (s)   | 5.4659 | 0.0408   | 5.4258 | 5.5218 | 0.75%            | Highly Stable      |
+------------------------------+--------+----------+--------+--------+------------------+--------------------+
| Route Withdrawal Latency (s) | 9.0427 | 0.1150   | 8.8960 | 9.1770 | 1.27%            | Highly Stable      |
+------------------------------+--------+----------+--------+--------+------------------+--------------------+
| Route Recovery Latency (s)   | 1.3943 | 0.0403   | 1.3510 | 1.4480 | 2.89%            | Highly Stable      |
+------------------------------+--------+----------+--------+--------+------------------+--------------------+
| Updates per 3 Flap Cycles    | 7.0000 | 0.8165   | 6.0000 | 8.0000 | 11.66%           | Stable             |
+------------------------------+--------+----------+--------+--------+------------------+--------------------+
| Data Plane PDR (%)           | 100.0% | -        | -      | -      | -                | 0% Packet Loss     |
+------------------------------+--------+----------+--------+--------+------------------+--------------------+
| Data Plane Avg RTT (ms)      | 0.18ms | -        | 0.09ms | 0.27ms | -                | Direct Peering     |
+------------------------------+--------+----------+--------+--------+------------------+--------------------+
| AS65003 Baseline Memory      | 23.07M | -        | -      | -      | -                | Low RSS Footprint  |
+------------------------------+--------+----------+--------+--------+------------------+--------------------+
| AS65003 Baseline CPU         | 0.00%  | -        | -      | -      | -                | Idle State         |
+------------------------------+--------+----------+--------+--------+------------------+--------------------+
```

---

## 5. Detailed Analysis of Baseline Scenarios

### Scenario 1: Cold Start Convergence
- **Observation:** Full container restart to eBGP session establishment and RIB route installation completed in **5.47 seconds**.
- **Run-to-Run Variance:** Extremely low ($CV = 0.75\%$), demonstrating that the test harness and daemon startup timings are consistent.

### Scenario 2: Link Failure & Recovery Dynamics
- **Route Withdrawal Latency:** Measured at **9.04 seconds**. This corresponds directly to the configured BGP Hold-Timer ($9\text{s}$), confirming that standard BGP relies solely on passive keepalive expiration to discover silent link failures.
- **Route Recovery Latency:** Once the link was restored, the BGP OPEN/KEEPALIVE handshake and UPDATE exchange re-converged the RIB in **1.39 seconds**.

### Scenario 3: Route Flapping & Oscillation Churn
- **Observation:** Injected 3 periodic link toggle cycles (1.5s down/up).
- **Result:** Generated an average of **7.0 BGP messages** received at AS 65003, with an oscillation frequency of approximately **15 flaps/min** during perturbation.

### Scenario 4: Data Plane Reachability & Packet Delivery Ratio (PDR)
- **Observation:** 10 ICMP echo requests transmitted across the 2-hop transit path (`AS 65003 -> AS 65002 -> AS 65001`).
- **Result:** **100% PDR** ($0\%$ packet loss) with sub-millisecond average latency ($0.18\text{ ms}$).

### Scenario 5: Control-Plane Memory & CPU Utilization
- **Observation:** Memory RSS remained flat at **~23.07 MiB** on AS 65003 with **~0.00% - 0.19% CPU** usage during steady-state.

---

## 6. Generated Visualizations & Data Artifacts

All experimental data and plots were exported to the repository:

1. **Summary JSON**: [`experiments/results/baseline_summary.json`](file:///c:/Users/pebu/OneDrive/Documents/sem%205/NDC%20project/experiments/results/baseline_summary.json)
2. **Tabular CSV**: [`experiments/results/baseline_summary.csv`](file:///c:/Users/pebu/OneDrive/Documents/sem%205/NDC%20project/experiments/results/baseline_summary.csv)
3. **Convergence Latency Plot**: [`experiments/results/figures/baseline_latencies.png`](file:///c:/Users/pebu/OneDrive/Documents/sem%205/NDC%20project/experiments/results/figures/baseline_latencies.png)
4. **Node Memory Overhead Plot**: [`experiments/results/figures/baseline_memory.png`](file:///c:/Users/pebu/OneDrive/Documents/sem%205/NDC%20project/experiments/results/figures/baseline_memory.png)

---

## 7. Next Steps: Month 2 (Weeks 5–6)
With robust baseline reference figures recorded:
- Develop the **Asynchronous Python AI Agent** alongside AS 65003.
- Build the **Feature Extraction Engine** (temporal metrics, AS-path edit distance, flap frequency).
- Train lightweight **Random Forest & Logistic Regression classifiers** to classify routing behavior into: *Normal, Suspicious, Route Leak Candidate, Prefix Hijack Candidate*.
