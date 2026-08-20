# AI-Enhanced BGP Autonomous Control Plane

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-green.svg)](https://www.docker.com/)
[![FRRouting](https://img.shields.io/badge/FRRouting-10.2.1-orange.svg)](https://frrouting.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An intelligent, autonomous, and standards-compliant BGP control-plane enhancement that detects and mitigates routing anomalies (prefix hijacks, sub-prefix deaggregations, route leaks, and flapping bursts) in real time using Machine Learning and dynamic BGP Local Preference policies with Shadow Validation, Deep RIB Verification, and Multi-Criteria Autonomous Rollback.

---

## 📌 Architecture & System Overview

```
+---------------------------------------------------------------------------------------------------+
|                                 SYNCHRONOUS AUTONOMOUS CONTROL PLANE                              |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [ FRRouting Multi-AS Testbed ] (AS 65001 -> AS 65002 Transit -> AS 65003 Monitor <- AS 65004)   |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ Telemetry Ingestion ] (vtysh collector + sliding-window buffer + SQLite/JSONL)                |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ 10-Feature Behavioral Extractor ] (Gao-Rexford valley-free heuristic + AS-Path Levenshtein)   |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ Calibrated ML Model & Multi-Factor Behavioral Trust Engine ] (CalibratedClassifierCV)         |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ Shadow Validator & Anti-Thrashing Guard ] (4s Staging Queue + Hysteresis Band Δ=0.05)          |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ Policy Engine, Deep RIB Verification & SQLite State Store ]                                    |
|     ├── Normal (Trust ≥ 0.85)     ──► LocalPref 100                                              |
|     ├── Suspicious (0.55 - 0.80)  ──► LocalPref 80 (Soft Deprioritization)                       |
|     ├── Route Leak (0.25 - 0.55)  ──► LocalPref 50 (Hard Deprioritization)                       |
|     └── Prefix Hijack (< 0.25)    ──► LocalPref 0 + BGP Community 'no-export' (Dual Quarantine)  |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

> **Architecture Note**: The control plane operates as a **synchronous polling autonomous controller** (not an asynchronous event-driven framework). Each polling iteration sequentially ingests telemetry from FRR, extracts features, performs calibrated inference, evaluates multi-factor trust, and atomically enforces verified route-map and RIB updates. This design ensures deterministic state transitions and full reproducibility in research testbeds.

---

## 🎯 Key Features & Research Highlights

1. **Standards-Compliant BGP Control Plane**: Works seamlessly on top of RFC-standard BGP (FRRouting 10.2.1) without modifying protocol wire formats.
2. **Dual-Action Quarantine & Deprioritization**:
   - **Prefix Hijacks**: **`LocalPref 0`** + BGP community **`no-export`** (RFC 1997).
   - **Route Leaks**: **`LocalPref 50`** (Hard Deprioritization) ensuring alternative valid transit paths are preferred.
   - **Flapping / Churn**: **`LocalPref 80`** (Soft Deprioritization) dampening churn without dropping traffic.
3. **Shadow Validation & Anti-Thrashing Safeguards**: 
   - 4.0-second transient staging buffer with strict streak-breaking logic to discard false alarms.
   - Asymmetric hysteresis band ($\Delta = 0.05$) and 10.0s minimum dwell time to eliminate policy thrashing near threshold boundaries.
4. **Deep Two-Layer Verification**:
   - **Layer 1 (Config)**: Confirms route-map rules and prefix-lists are installed in FRR via `show route-map`.
   - **Layer 2 (RIB Behavior)**: Queries `show bgp ipv4 unicast <prefix> json` to verify the actual best-path entry won selection with the expected `locPrf` and `community`.
5. **Multi-Criteria Autonomous Rollback**: Reverts `LocalPref` to `100` only when ML classification is Normal, AS paths are stable, recent flaps are quiescent, and upstream reachability is verified.
6. **Robust ML Evaluation (Cross-Seed Holdout & Overlapping Distributions)**:
   - Models trained with realistic overlapping feature distributions (preventing artificial separability).
   - Evaluated on an independent cross-seed test set (`random_state=99`) and a dedicated false-positive challenge set.

---

## 📊 4-Way Comparative Evaluation Matrix (Benchmark Framework)

### Evidence-Level Classifications
To ensure scientific rigor and transparent comparability, every baseline configuration is explicitly tagged with its evidence level:
- **`EMPIRICAL`**: Live autonomous measurement on the four-AS FRR container testbed.
- **`EMULATED`**: RFC 6811 ingestion model (not a live deployed RPKI cache/validator).
- **`MODELLED`**: Static rule-based baseline with literature-derived thresholds.
- **`ANALYTICAL`**: Derived directly from the BGP protocol specification (no anomaly detection mechanism exists).

### Historical Incident Replay Disclaimer
Scenarios **S4**, **S5**, and **S6** are **topology-local behavioral replays**. They recreate the *behavioral signatures* (origin hijack pattern, valley-free route leak pattern) of the named historical incidents within the four-AS FRR laboratory topology. They are **not** direct reproductions of the actual global Internet-scale events.

| Scenario | Type | Standard BGP (RFC) `[ANALYTICAL]` | BGP + RPKI ROV (RFC 6811) `[EMULATED]` | Behavioural Heuristics `[MODELLED]` | Proposed AI Control Plane `[EMPIRICAL]` |
|---|---|---|---|---|---|
| **S1: Direct Prefix Hijack** | Synthetic | ❌ Propagated (0% PDR) | ✅ < 0.10s (100% PDR) | ✅ 0.50s (92% PDR) | ✅ **1.34s Quarantine (LP 0 + no-export)** |
| **S2: Sub-Prefix Hijack (/25)** | Synthetic | ❌ Propagated (0% PDR) | ❌ Missed (0% PDR) | ✅ 0.50s (92% PDR) | ✅ **4.92s Quarantine (LP 0 + no-export)** |
| **S3: Route Flapping Burst** | Synthetic | ❌ Churn (50% PDR) | ❌ Missed (0% PDR) | ✅ 0.50s (92% PDR) | ✅ **15.42s Deprioritize (LP 80)** |
| **S4: YouTube 2008 Hijack** | Behavioral Replay | ❌ Propagated (0% PDR) | ✅ < 0.10s (100% PDR) | ✅ 0.50s (92% PDR) | ✅ **4.93s Quarantine (LP 0 + no-export)** |
| **S5: Google 2017 Route Leak** | Behavioral Replay | ❌ Propagated (0% PDR) | ⚠️ *N/A (Out of Scope)* | ✅ 0.50s (92% PDR) | ✅ **1.54s Deprioritize (LP 50)** |
| **S6: Cloudflare 2019 Route Leak** | Behavioral Replay | ❌ Propagated (0% PDR) | ⚠️ *N/A (Out of Scope)* | ✅ 0.50s (92% PDR) | ✅ **1.49s Deprioritize (LP 50)** |

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
# Using pinned lockfile for reproducibility:
python -m pip install -r requirements.lock

# Or install from specifier:
python -m pip install -r requirements.txt
```

### 4. Deploy the 4-AS Docker Testbed
```bash
python scripts/deploy_docker.py up
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

### 2. Retrain ML Models (Cross-Seed Holdout & Overlapping Distributions)
```bash
python scripts/train_ai_models.py
```

### 3. Run Live MTTD / MTTM Benchmark
```bash
# Live measurement across scenarios:
python scripts/run_live_benchmark.py --scenarios S1,S2,S3,S4,S5,S6 --trials 5

# Or offline dry-run with documented model values:
python scripts/run_live_benchmark.py --dry-run
```

### 4. Measure End-to-End Data-Plane PDR (Traffic Probing)
```bash
python scripts/measure_pdr.py --scenario S1
```

### 5. Run Failure Injection & Chaos Tests
```bash
# Toggle link:
python scripts/inject_failure.py link --node as65001 --interface eth0 --state down

# Simulate route flapping:
python scripts/inject_failure.py flap --node as65001 --interface eth0 --cycles 3

# Test controller crash recovery:
python scripts/inject_failure.py controller-crash --pid <PID>
```

### 6. Generate Environment & Reproducibility Manifest
```bash
python scripts/generate_manifest.py
```

### 7. Run Full Unit & Resilience Test Suite
```bash
python -m unittest discover tests/
```

---

## 📁 Repository Structure

```
.
├── config/                     # FRRouting daemon & vtysh configurations for ASes 65001-65004
├── data/                       # Telemetry databases and persistent state store
├── environment_manifest.json   # Machine-generated reproducibility manifest
├── experiments/                # Experimental benchmarking framework
│   ├── attacks/                # Programmable BGP attack injectors & historical signatures
│   ├── baseline/               # Baseline scenarios & latency profiling
│   ├── comparative/            # 4-way evaluation harness (Standard, RPKI, Heuristics, AI)
│   └── results/                # Quantitative JSON/CSV datasets and PNG figures
├── models/                     # Trained calibrated ML models and schema metadata
├── requirements.lock           # Exact pinned dependency lockfile
├── requirements.txt            # Python dependency specifiers
├── scripts/                    # Master CLI runners, benchmarks, and chaos injectors
│   ├── generate_evaluation_artifacts.py # Benchmark table generator with evidence levels
│   ├── generate_manifest.py    # Generates environment_manifest.json
│   ├── inject_failure.py       # Link, session, controller-crash & DB chaos utility
│   ├── measure_pdr.py          # End-to-end ICMP data-plane traffic probe
│   ├── run_autonomous_controller.py # Synchronous polling closed-loop controller
│   ├── run_live_benchmark.py   # Live MTTD/MTTM measurement harness
│   └── train_ai_models.py      # Retrains RF/LR with cross-seed holdout
├── src/                        # Core AI and Control Plane source code
│   ├── ai/                     # Feature extractor, classifiers, and hybrid trust engine
│   ├── dataset/                # Overlapping dataset generator & training pipeline
│   ├── policy/                 # Policy engine, shadow validator, rollback, state store
│   ├── telemetry/              # FRR collector, sliding window buffer, SQLite storage
│   └── utils/                  # Logging and system profiling utilities
├── tests/                      # Full test suite
│   ├── test_classifier.py
│   ├── test_failure_resilience.py # Controller-level resilience tests (timeout, malformed JSON, etc.)
│   ├── test_feature_extractor.py
│   ├── test_policy_engine.py
│   ├── test_rib_verification.py   # Deep RIB best-path verification tests
│   ├── test_shadow_rollback.py
│   ├── test_state_and_verification.py
│   ├── test_state_store_events.py # Detection & mitigation timestamp event tests
│   └── test_telemetry_sync.py
├── topologies/                 # Docker Compose & Containerlab manifests
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
