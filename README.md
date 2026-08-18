# AI-Enhanced BGP Autonomous Control Plane

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-green.svg)](https://www.docker.com/)
[![FRRouting](https://img.shields.io/badge/FRRouting-10.2.1-orange.svg)](https://frrouting.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An intelligent, autonomous, and standards-compliant BGP control-plane enhancement that detects and mitigates routing anomalies (prefix hijacks, sub-prefix deaggregations, route leaks, and flapping bursts) in real time using Machine Learning and dynamic BGP Local Preference policies with Shadow Validation and Multi-Criteria Autonomous Rollback.

---

## 📌 Architecture & System Overview

```
+---------------------------------------------------------------------------------------------------+
|                                     AI CONTROL PLANE ARCHITECTURE                                 |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [ FRRouting Multi-AS Testbed ] (AS 65001 -> AS 65002 Transit -> AS 65003 Monitor <- AS 65004)   |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ Resilient Telemetry Ingestion ] (vtysh collector + sliding-window buffer + SQLite/JSONL)       |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ 10-Feature Behavioral Extractor ] (Gao-Rexford valley-free heuristic + AS-Path Levenshtein)   |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ Calibrated ML Model & Multi-Factor Behavioral Trust Engine ] (CalibratedClassifierCV)         |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ Shadow Validator & Anti-Thrashing Guard ] (5s Staging Queue + Hysteresis Band Δ=0.05)         |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ Policy Engine, Verified FRR Enforcement & SQLite State Store ]                                 |
|     ├── Normal (Trust ≥ 0.85)     ──► LocalPref 100                                              |
|     ├── Suspicious (0.55 - 0.80)  ──► LocalPref 80 (Soft Deprioritization)                       |
|     ├── Route Leak (0.25 - 0.55)  ──► LocalPref 50 (Hard Deprioritization)                       |
|     └── Prefix Hijack (< 0.25)    ──► LocalPref 0 + BGP Community 'no-export' (Dual Quarantine)  |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 🎯 Key Features & Research Highlights

1. **Standards-Compliant BGP Control Plane**: Works seamlessly on top of RFC-standard BGP (FRRouting 10.2.1) without modifying protocol wire formats.
2. **Dual-Action Quarantine**: Combines **`LocalPref 0`** with standard BGP community **`no-export`** (RFC 1997), guaranteeing both local forwarding suppression and prevention of downstream leak propagation.
3. **Shadow Validation & Anti-Thrashing Safeguards**: 
   - 5.0-second transient staging buffer with strict streak-breaking logic to discard false alarms.
   - Asymmetric hysteresis band ($\Delta = 0.05$) and 10.0s minimum dwell time to eliminate policy thrashing near threshold boundaries.
4. **Multi-Criteria Autonomous Rollback**: Reverts `LocalPref` to `100` only when ML classification is Normal, AS paths are stable, recent flaps are quiescent, and upstream reachability is verified.
5. **Relationship-Aware Gao-Rexford Analysis**: Implements RFC 9234 customer-provider-peer business relationship state machines to catch complex transit route leaks.
6. **Controlled Historical Signature Replays**: Evaluated against faithful topological anomaly signatures of major Internet incidents:
   - *Pakistan Telecom / YouTube Prefix Hijack (2008)*
   - *Google / Rostelecom Route Leak (2017)*
   - *Cloudflare / Verizon Route Leak (2019)*

---

## 📊 4-Way Comparative Benchmark Matrix (Preliminary Week-8 Benchmarks)

> **Note on Comparative Positioning**: RPKI Route Origin Validation (ROV - RFC 6811) provides near-instantaneous ($0.05\text{s}$) mitigation for origin-based prefix hijacks, but is fundamentally out of scope for route leaks (S5, S6) because the origin AS remains cryptographically valid. The proposed AI control plane provides comprehensive coverage across all 6 attack classes.

| Scenario | Standard BGP | BGP + RPKI ROV (RFC 6811) | Behavioural Heuristics | Proposed AI Control Plane |
|---|---|---|---|---|
| **S1: Direct Prefix Hijack** | ❌ Missed (0% PDR) | ✅ 0.05s (100% PDR) | ✅ 0.62s (92% PDR) | ✅ **1.34s Quarantine** (100% PDR) |
| **S2: Sub-Prefix Hijack (/25)** | ❌ Missed (0% PDR) | ❌ Missed (0% PDR) | ✅ 0.63s (92% PDR) | ✅ **4.92s Quarantine** (100% PDR) |
| **S3: Route Flapping Burst** | ❌ Missed (50% PDR) | ❌ Missed (0% PDR) | ✅ 4.39s (92% PDR) | ✅ **15.42s Deprioritize** (100% PDR) |
| **S4: YouTube 2008 Hijack** | ❌ Missed (0% PDR) | ✅ 0.05s (100% PDR) | ✅ 0.63s (92% PDR) | ✅ **4.93s Quarantine** (100% PDR) |
| **S5: Google 2017 Route Leak** | ❌ Missed (0% PDR) | ⚠️ *N/A (Out of Scope)* | ✅ 0.65s (92% PDR) | ✅ **1.54s Quarantine** (100% PDR) |
| **S6: Cloudflare 2019 Route Leak** | ❌ Missed (0% PDR) | ⚠️ *N/A (Out of Scope)* | ✅ 0.64s (92% PDR) | ✅ **1.49s Quarantine** (100% PDR) |

---

## 🚀 Quickstart & Installation

### 1. Prerequisites
- **Python**: 3.10 or higher
- **Docker Desktop**: Running with Linux containers
- **Git**

### 2. Clone the Repository
```bash
git clone https://github.com/Sudalai-kumar/AI-Enhanced-BGP.git
cd "NDC project"
```

### 3. Install Python Dependencies
```bash
python -m pip install -r requirements.txt
```

### 4. Deploy the 4-AS Docker Testbed
```bash
python scripts/deploy_docker.py up
# or: python scripts/deploy_docker.py --action up
```

Verify that all 4 FRR containers (`as65001`, `as65002`, `as65003`, `as65004`) are healthy:
```bash
python scripts/verify_convergence.py
```

---

## 🛠️ How to Use

### 1. Run the Autonomous BGP Controller
Launch the closed-loop autonomous daemon on monitor node `as65003`:
```bash
python scripts/run_autonomous_controller.py --router as65003
```

### 2. Verify Live Anomaly Quarantine & Multi-Criteria Rollback
Run the automated end-to-end perturbation test:
```bash
python scripts/verify_live_lifecycle.py
```

### 3. Run the Full 4-Way Attack Evaluation Suite
Execute the multi-iteration comparative benchmark across all 6 scenarios:
```bash
python scripts/run_attack_simulations.py --iterations 3
```

### 4. Generate Publication-Quality Plots
Generate comparative PDR and MTTM latency graphs:
```bash
python scripts/plot_attack_evaluation.py
```

### 5. Run Unit & Synchronization Tests
```bash
python -m unittest discover tests/
```

---

## 📁 Repository Structure

```
.
├── config/                     # FRRouting daemon & vtysh configurations for ASes 65001-65004
├── experiments/                # Experimental benchmarking framework
│   ├── attacks/                # Programmable BGP attack injectors & historical signatures
│   ├── baseline/               # Baseline scenarios & latency profiling
│   ├── comparative/            # 4-way evaluation harness (Standard, RPKI, Heuristics, AI)
│   └── results/                # Quantitative JSON/CSV datasets and PNG figures
├── models/                     # Trained calibrated ML models and schema metadata
├── scripts/                    # Master CLI runners, deploy scripts, and lifecycle testers
├── src/                        # Core AI and Control Plane source code
│   ├── ai/                     # Feature extractor, classifiers, and hybrid trust engine
│   ├── policy/                 # Policy engine, shadow validator, rollback manager, and SQLite state store
│   ├── telemetry/              # FRR collector, sliding window buffer, and SQLite storage
│   └── utils/                  # Logging and system profiling utilities
├── tests/                      # Unit test suites (Policy, Shadow, Classifier, Feature Extractor)
├── topologies/                 # Docker Compose & Containerlab manifests
├── requirements.txt            # Python dependencies
└── README.md                   # Complete documentation
```

---

## 👥 Authors & Academic Context

Developed as part of the **AI-Enhanced BGP Autonomous Control Plane Project**:
- **Authors**: M Sudalai Kumar, B Satlas Rohit, S Ajay Kumar, S Srinivasan
- **Supervisor / Institution**: Department of Network Engineering & Data Communications

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
