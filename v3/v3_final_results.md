# v3 Final Results — AI-Enhanced BGP Anomaly Detection & Autonomous Mitigation

**Generated:** 2026-09-06T14:50:17Z
**Commit:** `03cfccf6b49efaf9b04d18451dde13ff8811e793`
**Topology:** 10-AS FRR (as65001–as65010), Docker Desktop 29.7.2, FRR 10.2.1
**Platform:** Windows 11 + Python 3.13.5

---

## 1. What Did We Build?

A **10-AS decentralised BGP anomaly detection and autonomous mitigation system** consisting of:

| Component | Implementation |
|-----------|---------------|
| **10-node topology** | `as65001`–`as65010`, 18 eBGP sessions across 3 tiers (Tier-1 transit core, Tier-2 regional, Tier-3 stub) |
| **Dual autonomous controllers** | `as65001` (core), `as65003` (edge defender), operating independently |
| **Rogue node** | `as65010` — injects prefix hijacks via transit path `as65010->as65006->as65002->as65001` |
| **5-stage async pipeline** | Telemetry -> Feature extraction -> ML inference -> Shadow validation -> Policy actor |
| **Empirical training dataset** | 435 samples from live FRR testbed (SHA-256: `3f05be18...`) |
| **AI models** | Calibrated Random Forest + Logistic Regression, trained on 348 samples, tested on 87 |
| **Policy enforcement** | FRR route-map injection: `LocalPref 0 + no-export` (quarantine) or `LocalPref 50` (deprioritise) |

---

## 2. How Does It Work?

### Detection Pipeline (0.5s polling cycle)
1. **Telemetry loop** — `FRRTelemetryCollector` polls `vtysh show bgp ipv4 unicast json`, records 5-minute sliding window per prefix.
2. **Feature extraction** — 10-feature vector: AS-path length, edit distance vs baseline, origin AS change, prefix mask length, announcements/min, 5-min flap count, LocalPref, route age, valley-free violation, neighbor diversity.
3. **ML inference** — Calibrated Random Forest classifies into 4 classes: Normal (0), Suspicious (1), Route Leak (2), Prefix Hijack (3).
4. **Hybrid trust scoring** — 6-factor weighted trust score (0.0–1.0): origin 20%, path 20%, flap 15%, prefix specificity 15%, peer diversity 10%, ML confidence 20%.
5. **Shadow validator** — Requires N consistent anomaly votes before policy promotion (bypassed for immediate-quarantine class).
6. **Policy actor** — Atomic FRR route-map commit with RIB verification; withdrawal events trigger immediate quarantine release.

### Mitigation & Recovery
- **Quarantine:** LocalPref -> 0 + `no-export` community injected via vtysh route-map.
- **Rollback:** Route withdrawal detection triggers immediate policy removal. Multi-criteria recovery streak (3 consecutive normal ticks + stable origin + quiescent flaps + peer reachability) triggers autonomous rollback to LP 100.

---

## 3. Does It Actually Work?

### Live Closed-Loop Lifecycle Test (script: `scripts/verify_live_lifecycle.py`)

Attack: Sub-prefix hijack `192.0.2.0/25` injected on `as65010`.

```
===========================================================================
 10-AS LIVE LIFECYCLE SUMMARY
===========================================================================
1. Detection Latency (MTTD):               1.400s
2. Mitigation Latency (MTTM):              2.793s
3. Dual Quarantine (LP 0 + no-export):     PASS
4. Autonomous Rollback to LP 100:          PASS
===========================================================================
```

**Phase 3 RIB verification** confirmed quarantine was applied in FRR:
```
BGP routing table entry for 192.0.2.0/25
  localpref 0, Community: no-export
  Not advertised to any peer
```

### Unit Test Suite

```
Ran 50 tests in 11.264s
OK (skipped=1)
```

---

## 4. How Well Does It Work? (S1-S6, 5 Trials Each, Live Testbed)

| Scenario | MTTD (mean±std) | MTTM (mean±std) | PDR | Action Applied |
|----------|----------------|----------------|-----|----------------|
| S1: Direct Prefix Hijack (192.0.2.0/24) | 4.12s ±0.0 | 5.44s ±0.0 | 20% | LocalPref 50 |
| **S2: Sub-Prefix Hijack (192.0.2.0/25)** | **0.44s ±0.0** | **1.68s ±0.03** | **100%** | **LP 0 + no-export** |
| S3: Route Flapping Burst | 5.93s ±1.94 | 7.18s ±1.97 | 80% | LocalPref 50 |
| **S4: YouTube 2008 Replay (208.65.153.0/24)** | **0.45s ±0.0** | **1.69s ±0.01** | **100%** | **LP 0 + no-export** |
| S5: Google/Rostelecom Route Leak (2017) | 4.21s ±0.0 | 5.48s ±0.0 | 20% | LocalPref 50 |
| S6: Cloudflare/Verizon Route Leak (2019) | 5.53s ±1.35 | 6.79s ±1.33 | 40% | LocalPref 50 |

> **PDR interpretation:** S2/S4 achieve 100% PDR (full quarantine + no-export blocking downstream propagation). S1/S3/S5/S6 are detected and deprioritised (LocalPref 50). RPKI blindspot: S2, S3, S5, S6 are all undetected by RPKI ROV (outside its origin-validation scope).

### 4-Way Comparative Matrix Highlights

| Scenario | Standard BGP | RPKI ROV | Heuristics | **AI (Proposed)** |
|----------|-------------|----------|------------|-------------------|
| S2 (Sub-prefix) | No | No (blind) | No | Yes — MTTD=0.44s, PDR=100% |
| S3 (Flapping) | No | No | No | Yes — MTTD=5.93s, PDR=80% |
| S4 (YouTube 2008) | No | Yes ROV | No | Yes — MTTD=0.45s, PDR=100% |
| S5 (Route Leak) | No | No (scope) | No | Yes — MTTD=4.21s, PDR=20% |
| S6 (Route Leak) | No | No (scope) | No | Yes — MTTD=5.53s, PDR=40% |

---

## 5. AI Model Performance (Empirical Holdout — Trial 5)

| Metric | Random Forest | Logistic Regression |
|--------|--------------|---------------------|
| Accuracy | 85.06% | 79.31% |
| Weighted F1 | 0.8141 | 0.7817 |
| Macro F1 | 0.4542 | 0.4301 |
| Hijack (Class 3) Precision | 1.00 | 1.00 |
| Hijack (Class 3) Recall | 0.833 | 0.722 |
| Hijack (Class 3) F1 | 0.909 | 0.839 |
| False Positive Rate (Normal->Attack) | **3.2%** | 100% (collapse) |

> Logistic Regression exhibits calibration collapse on the FPR challenge set; Random Forest is the production model.

**Training commit:** `03cfccf6b49efaf9b04d18451dde13ff8811e793`
**Dataset SHA-256:** `3f05be18c1e8ee7d78039fdf76784ff1ecabf8813c6bb55c69416a7638a9437b`
**RF model SHA-256:** `4562d4adc1ac8cc9ae44ff0579fa15f11065c17f76fc24598584998a2980430e`

---

## 6. What Is Genuinely New in v3?

| v2 | v3 |
|----|----|
| 4-AS topology | **10-AS 3-tier topology** (65001-65010) |
| Single controller | **Dual decentralised controllers** (core + edge defender) |
| Synthetic training only | **435-sample empirical FRR dataset** (all 8 scenarios, 5 trials each) |
| Policy based on hardcoded rules | **ML + hybrid trust score + shadow validator** |
| Manual rollback | **Autonomous rollback on route withdrawal + multi-criteria recovery** |
| No withdrawal handling | **Route withdrawal events clear quarantine state in <2s** |
| No attack diversity | **S1-S6 including historical incident behavioral replays (YouTube 2008, Google 2017, Cloudflare 2019)** |
| Tests: 32 | **Tests: 50 (49 pass, 1 skipped)** |

---

## 7. Environment Manifest

| Field | Value |
|-------|-------|
| Git commit | `03cfccf6b49efaf9b04d18451dde13ff8811e793` |
| FRR image | `quay.io/frrouting/frr:10.2.1` |
| FRR image digest | `sha256:e47e67bd...` |
| Docker version | 29.7.2 |
| Python | 3.13.5 |
| Dataset SHA-256 | `3f05be18...` |
| RF model SHA-256 | `4562d4ad...` |
| LR model SHA-256 | `bed0e001...` |

---

## 8. Evidence Package Contents

```
v3/
├── topology/
│   ├── deploy_docker.py       # 10-AS deployment script
│   ├── deploy.sh              # Shell deployment helper
│   ├── verify_convergence.py  # 10-AS/18-session convergence verifier
│   └── test_10as_topology.py  # Topology unit tests
├── empirical_training_dataset/
│   └── bgp_real_training.jsonl  (435 samples, SHA-256 verified)
├── trained_models/
│   ├── random_forest.joblib
│   ├── logistic_regression.joblib
│   ├── scaler.joblib
│   └── model_metadata.json
├── benchmark_results/
│   ├── attack_evaluation_results.json   (S1-S6, 5 trials each)
│   ├── attack_evaluation_results.csv
│   └── model_training_evaluation.json   (confusion matrix, F1, FPR)
├── attack_trials/
│   ├── controller_state_as65001.db
│   └── controller_state_as65003.db
├── RIB_verification_logs/
│   ├── as65001_bgp_summary.txt
│   ├── as65001_rib.txt
│   ├── as65003_bgp_summary.txt
│   ├── as65003_rib.txt
│   ├── as65010_bgp_summary.txt
│   └── as65010_rib.txt
├── environment_manifest.json
└── v3_final_results.md        (this file)
```
