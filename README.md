# AI-Enhanced BGP Autonomous Control Plane (v3.0)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-green.svg)](https://www.docker.com/)
[![FRRouting](https://img.shields.io/badge/FRRouting-10.2.1-orange.svg)](https://frrouting.org/)
[![Topology](https://img.shields.io/badge/Topology-10--AS%20Multi--Tier-purple.svg)](topologies/docker-compose.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An intelligent, autonomous, and RFC-compliant BGP control-plane enhancement that detects and mitigates routing anomalies (prefix hijacks, sub-prefix deaggregations, route leaks, and flapping bursts) in real time using Machine Learning and dynamic BGP Local Preference policies with Shadow Validation, Deep RIB Verification, Multi-Criteria Autonomous Rollback, and Decentralized Multi-Tier Defense.

---

## 📌 Architecture & System Overview

```
+===================================================================================================+
|                    10-AS MULTI-TIER BGP TOPOLOGY & DUAL AUTONOMOUS DEFENSE                        |
+===================================================================================================+
|                                                                                                   |
|               [ AS65005 ]                      [ AS65006 Transit ] <--- [ AS65010 Rogue AS ]      |
|                    ▲                                    ▲                                         |
|                    │ (Provider-Customer)                │ (Provider-Customer)                     |
|                    ▼                                    ▼                                         |
|         +------------------------------------------------------+                                  |
|         |           AS65002 Tier-1 Transit Backbone            |                                  |
|         +------------------------------------------------------+                                  |
|                                    ▲                                                              |
|                                    │ (Peer-to-Peer Transit)                                       |
|                                    ▼                                                              |
|         +------------------------------------------------------+                                  |
|         |  AS65001 Tier-1 Backbone [CORE DEFENDER CONTROLLER]  |                                  |
|         +------------------------------------------------------+                                  |
|                    ▲                                    ▲                                         |
|                    │                                    │ (Provider-Customer)                     |
|                    ▼                                    ▼                                         |
|         +--------------------+               +--------------------+                               |
|         |  AS65003 Regional  |               |  AS65004 Regional  |                               |
|         |  [EDGE DEFENDER]   |               +--------------------+                               |
|         +--------------------+                          ▲                                         |
|              ▲          ▲                               │ (Provider-Customer)                     |
|              │          │                               ▼                                         |
|              ▼          ▼                      +--------------------+                             |
|         +---------+ +---------+                |  AS65009 Stub Cust |                             |
|         | AS65007 | | AS65008 |                +--------------------+                             |
|         | Origin  | | Stub    |                                                                   |
|         +---------+ +---------+                                                                   |
|                                                                                                   |
+===================================================================================================+
|                                  AUTONOMOUS CONTROL PLANE PIPELINE                                 |
+===================================================================================================+
|                                                                                                   |
|  [ Telemetry Coroutine ] ──► Async vtysh collector (show bgp summary & ipv4 unicast)             |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ 10-Feature Behavioral Extractor + Calibrated ML Model & Hybrid Trust Engine ]                  |
|     ├── 1. AS-Path Hop Count            6. Rolling 5-Min Flap Count                               |
|     ├── 2. AS-Path Edit Distance        7. Current Local Preference                               |
|     ├── 3. Origin AS Change Flag        8. True Route Maturity (Age)                              |
|     ├── 4. Prefix CIDR Mask Length      9. Gao-Rexford Valley-Free Violation                      |
|     └── 5. Announcements / Minute      10. Peer Neighbor Diversity Ratio                          |
|                 │                                                                                 |
|                 ▼                                                                                 |
|  [ Dedicated Policy Actor ] (Shadow Validator & Anti-Thrashing Guard + Atomic Apply)              |
|     ├── Normal (Trust ≥ 0.85)     ──► LocalPref 100                                              |
|     ├── Suspicious (0.55 - 0.80)  ──► LocalPref 80 (Soft Deprioritization)                       |
|     ├── Route Leak (0.25 - 0.55)  ──► LocalPref 50 (Hard Deprioritization)                       |
|     └── Prefix Hijack (< 0.25)    ──► LocalPref 0 + BGP Community 'no-export' (Dual Quarantine)  |
|                                                                                                   |
|  [ Deep Two-Layer RIB Verification ] ──► Layer 1 (Config) + Layer 2 (Active FIB/RIB Best-Path)    |
|  [ Multi-Criteria Rollback Engine ]  ──► Autonomous Reversion to LP 100 upon Sustained Health     |
|                                                                                                   |
+===================================================================================================+
```

---

## 🎯 Key Features & Research Highlights

1. **10-AS Multi-Tier Testbed**: Emulates a complete carrier-scale hierarchy featuring Tier-1 Transit Backbones (AS65001, AS65002), Regional Hubs (AS65003, AS65004, AS65005, AS65006), Multi-Homed Customer Stubs (AS65007, AS65008, AS65009), and a Rogue Adversary (AS65010).
2. **Decentralized Dual Control Planes**:
   - **Core Defender (AS65001)**: First line of defense stopping cross-backbone transit leaks and wide-area route contamination.
   - **Edge Defender (AS65003)**: Second line of defense ensuring customer stub traffic isolation and protecting enterprise origins.
3. **Standards-Compliant Dual-Action Quarantine**:
   - **Prefix Hijacks**: **`LocalPref 0`** + RFC 1997 **`no-export`** community.
   - **Route Leaks**: **`LocalPref 50`** (Hard Deprioritization) ensuring alternative valid transit paths are preferred.
   - **Flapping / Churn**: **`LocalPref 80`** (Soft Deprioritization) dampening churn without packet loss.
4. **Empirical Telemetry Training Pipeline**: Real-time training from 10-AS live testbed measurements (`bgp_real_training.jsonl`) with chronological and trial-based evaluation splits.
5. **Deep Two-Layer Verification**:
   - **Layer 1 (Config)**: Confirms route-map and prefix-list syntax applied to FRR via `show route-map`.
   - **Layer 2 (RIB Behavior)**: Verifies that the target prefix in `show bgp ipv4 unicast <prefix> json` actually won best-path selection with the expected `locPrf` and `community`.
6. **Shadow Validation & Anti-Thrashing Safeguards**: 
   - Transient staging buffer with streak-breaking logic to discard transient flapping false alarms.
   - Asymmetric hysteresis band ($\Delta = 0.05$) and minimum dwell time to eliminate policy oscillation near decision boundaries.

---

## 📊 4-Way Comparative Evaluation Matrix

| Scenario | Attack Type | Standard BGP (RFC) `[ANALYTICAL]` | BGP + RPKI ROV (RFC 6811) `[EMULATED]` | Behavioural Heuristics `[MODELLED]` | Proposed AI Control Plane `[EMPIRICAL]` |
|---|---|---|---|---|---|
| **S1: Direct Prefix Hijack** | Origin Hijack | ❌ Propagated (0% PDR) | ✅ < 0.10s (100% PDR) | ✅ 0.50s (92% PDR) | ✅ **Quarantine (LP 0 + no-export)** |
| **S2: Sub-Prefix Hijack (/25)** | Deaggregation | ❌ Propagated (0% PDR) | ❌ Missed (0% PDR) | ✅ 0.50s (92% PDR) | ✅ **Quarantine (LP 0 + no-export)** |
| **S3: Route Flapping Burst** | Churn Flood | ❌ Churn (50% PDR) | ❌ Missed (0% PDR) | ✅ 0.50s (92% PDR) | ✅ **Deprioritize (LP 80)** |
| **S4: YouTube 2008 Hijack** | Historical Replay | ❌ Propagated (0% PDR) | ✅ < 0.10s (100% PDR) | ✅ 0.50s (92% PDR) | ✅ **Quarantine (LP 0 + no-export)** |
| **S5: Google 2017 Route Leak** | Route Leak | ❌ Propagated (0% PDR) | ⚠️ *N/A (Out of Scope)* | ✅ 0.50s (92% PDR) | ✅ **Deprioritize (LP 50)** |
| **S6: Cloudflare 2019 Route Leak** | Route Leak | ❌ Propagated (0% PDR) | ⚠️ *N/A (Out of Scope)* | ✅ 0.50s (92% PDR) | ✅ **Deprioritize (LP 50)** |

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
python -m pip install -r requirements.lock
```

### 4. Deploy the 10-AS Docker Testbed
```bash
python scripts/deploy_docker.py up
```

Verify that all 10 FRR nodes (`as65001` through `as65010`) and 18 eBGP sessions are converged:
```bash
python scripts/verify_convergence.py
```

---

## 🛠️ Operational Workflows

### 1. Run Dual Autonomous Controllers (Core + Edge Defense)
Launch concurrent autonomous control planes for AS65001 (Core Defender) and AS65003 (Edge Defender):
```bash
python scripts/run_dual_controller.py --interval 1.0 --model random_forest
```

### 2. Collect Empirical Telemetry from the 10-AS Testbed
Execute multi-vantage empirical telemetry collection:
```bash
python scripts/collect_training_data.py --trials 5 --duration 5.0
```

### 3. Train Calibrated AI Models on Empirical 10-AS Data
Train and evaluate Random Forest and Logistic Regression on empirical telemetry:
```bash
python scripts/train_ai_models.py --real-data
```

### 4. Run Live MTTD / MTTM / PDR Benchmarks
Execute the multi-trial live benchmark harness:
```bash
python scripts/run_live_benchmark.py --scenarios S1,S2,S3,S4,S5,S6 --trials 5
```

### 5. Validate End-to-End Closed-Loop Lifecycle
Run the automated Anomaly $\to$ Detection $\to$ Quarantine $\to$ Rollback verification:
```bash
python scripts/verify_live_lifecycle.py
```

### 6. Generate Reproducibility Manifest
```bash
python scripts/generate_manifest.py
```

### 7. Run Complete Unit Test Suite
```bash
python -m unittest discover tests/
```

---

## 📁 Repository Structure

```
.
├── config/                     # FRRouting daemons & vtysh configs for all 10 ASes (65001-65010)
├── data/                       # Telemetry databases and persistent state stores
├── environment_manifest.json   # Machine-generated reproducibility manifest
├── experiments/                # Experimental benchmarking framework
│   ├── attacks/                # Programmable BGP attack injectors & historical signatures
│   ├── baseline/               # Baseline scenarios & latency profiling
│   ├── comparative/            # 4-way evaluation harness (Standard, RPKI, Heuristics, AI)
│   └── results/                # Quantitative JSON/CSV datasets and PNG figures
├── models/                     # Trained calibrated ML models and metadata
├── requirements.lock           # Exact pinned dependency lockfile
├── requirements.txt            # Python dependency specifiers
├── scripts/                    # Master CLI runners, benchmarks, and data collection
│   ├── collect_training_data.py # Dual-observer empirical data collection campaign
│   ├── deploy_docker.py        # 10-AS Docker Compose manager
│   ├── generate_manifest.py    # Generates environment_manifest.json
│   ├── inject_failure.py       # Link, session, and chaos utility
│   ├── measure_pdr.py          # Data-plane traffic probe
│   ├── run_autonomous_controller.py # Single-router autonomous controller
│   ├── run_dual_controller.py  # Dual decentralized controller (Core + Edge)
│   ├── run_live_benchmark.py   # Live MTTD/MTTM measurement harness
│   ├── train_ai_models.py      # Empirical & synthetic ML training CLI
│   ├── verify_convergence.py   # Full 10-AS convergence verification
│   └── verify_live_lifecycle.py # End-to-end closed-loop lifecycle verification
├── src/                        # Core source code
│   ├── ai/                     # 10-feature extractor, classifiers, hybrid trust engine
│   ├── dataset/                # Dataset generation and empirical training pipeline
│   ├── policy/                 # Policy engine, shadow validator, rollback, state store
│   ├── telemetry/              # FRR collector, sliding window buffer, SQLite storage
│   └── utils/                  # Logging and system utilities
├── tests/                      # Full test suite
├── topologies/                 # Docker Compose & Containerlab 10-AS manifests
└── v3/                         # Authoritative v3 results and evidence package
```

---

## 👥 Authors & Academic Context

Developed as part of the **AI-Enhanced BGP Autonomous Control Plane Project (v3.0)**:
- **Authors**: M Sudalai Kumar, B Satlas Rohit, S Ajay Kumar, S Srinivasan
- **Supervisor / Institution**: Department of Network Engineering & Data Communications

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
