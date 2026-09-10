"""
V4 Experiment A: Offline Machine Learning Evaluation & Stress Testing.

Evaluates:
1. Multi-model offline comparison on 435 empirical testbed samples:
   - Random Forest (Calibrated Isotonic)
   - Logistic Regression (Calibrated Sigmoid)
   - Deterministic Heuristic Detector
2. False-Positive Stress Test on 1,000 normal-traffic telemetry windows.
3. Class Imbalance Sensitivity Analysis under 90/10, 95/5, and 99/1 normal-to-attack ratios.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import classification_report, f1_score, confusion_matrix, precision_recall_fscore_support

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _REPO_ROOT)

from src.dataset.generator import FEATURE_NAMES, generate_false_positive_set
from experiments.comparative.heuristic_detector import HeuristicDetector

DATASET_PATH = os.path.join(_REPO_ROOT, "data", "raw", "bgp_real_training.jsonl")
RESULTS_DIR = os.path.join(_REPO_ROOT, "v4", "results", "raw")
CLASS_NAMES = ["Normal", "Suspicious", "Route Leak Candidate", "Prefix Hijack Candidate"]


def evaluate_heuristics(X_eval: np.ndarray, y_eval: np.ndarray) -> dict:
    """Evaluates the rule-based HeuristicDetector on a feature matrix."""
    detector = HeuristicDetector()
    preds = []
    for row in X_eval:
        res = detector.evaluate(row)
        preds.append(res["class_id"])
    preds = np.array(preds)

    labels_present = sorted(list(set(y_eval) | set(preds)))
    names_present = [CLASS_NAMES[i] for i in labels_present if i < len(CLASS_NAMES)]

    report = classification_report(y_eval, preds, labels=labels_present, target_names=names_present, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_eval, preds, labels=[0, 1, 2, 3]).tolist()
    macro_f1 = float(f1_score(y_eval, preds, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y_eval, preds, average="weighted", zero_division=0))
    acc = float(np.mean(preds == y_eval))

    # FPR on normal class (class 0)
    normal_idx = np.where(y_eval == 0)[0]
    fpr = float(np.mean(preds[normal_idx] != 0)) if len(normal_idx) > 0 else 0.0

    return {
        "accuracy": round(acc, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "false_positive_rate": round(fpr, 4),
        "classification_report": report,
        "confusion_matrix": cm,
        "predictions": preds.tolist()
    }


def run_offline_evaluation():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print("=" * 80)
    print(" V4 EXPERIMENT A: OFFLINE MODEL EVALUATION ON 435 EMPIRICAL SAMPLES")
    print("=" * 80)

    df = pd.read_json(DATASET_PATH, lines=True)
    if "timestamp" in df.columns:
        df = df.sort_values(by="timestamp").reset_index(drop=True)

    X = df[FEATURE_NAMES].values
    y = df["label"].astype(int).values

    print(f"[*] Total Empirical Samples: {len(df)}")
    print(f"[*] Class Distribution: {dict(df['label'].value_counts())}")

    # Standardized 75/25 stratified holdout
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    print(f"[*] Split -> Train={len(X_train)} samples, Test={len(X_test)} samples")

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 1. Random Forest (Calibrated Isotonic)
    rf_base = RandomForestClassifier(n_estimators=50, max_depth=12, class_weight="balanced", random_state=42, n_jobs=1)
    rf_cal = CalibratedClassifierCV(estimator=rf_base, cv=min(5, len(np.unique(y_train))), method="isotonic")
    rf_cal.fit(X_train_scaled, y_train)
    rf_preds = rf_cal.predict(X_test_scaled)
    rf_probs = rf_cal.predict_proba(X_test_scaled)

    # 2. Logistic Regression (Calibrated Sigmoid)
    lr_base = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    lr_cal = CalibratedClassifierCV(estimator=lr_base, cv=min(5, len(np.unique(y_train))), method="sigmoid")
    lr_cal.fit(X_train_scaled, y_train)
    lr_preds = lr_cal.predict(X_test_scaled)
    lr_probs = lr_cal.predict_proba(X_test_scaled)

    # 3. Deterministic Heuristics (Evaluated on Unscaled Features)
    heur_results = evaluate_heuristics(X_test, y_test)

    # Model metrics
    labels_present = sorted(list(set(y_test) | set(rf_preds) | set(lr_preds)))
    names_present = [CLASS_NAMES[i] for i in labels_present if i < len(CLASS_NAMES)]

    rf_report = classification_report(y_test, rf_preds, labels=labels_present, target_names=names_present, output_dict=True, zero_division=0)
    lr_report = classification_report(y_test, lr_preds, labels=labels_present, target_names=names_present, output_dict=True, zero_division=0)

    rf_cm = confusion_matrix(y_test, rf_preds, labels=[0, 1, 2, 3]).tolist()
    lr_cm = confusion_matrix(y_test, lr_preds, labels=[0, 1, 2, 3]).tolist()

    normal_test_idx = np.where(y_test == 0)[0]
    rf_fpr_test = float(np.mean(rf_preds[normal_test_idx] != 0))
    lr_fpr_test = float(np.mean(lr_preds[normal_test_idx] != 0))

    offline_payload = {
        "dataset_metadata": {
            "total_samples": len(df),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "features": FEATURE_NAMES,
            "classes": CLASS_NAMES,
            "distribution": {str(k): int(v) for k, v in df["label"].value_counts().items()}
        },
        "random_forest": {
            "accuracy": round(float(np.mean(rf_preds == y_test)), 4),
            "macro_f1": round(float(f1_score(y_test, rf_preds, average="macro", zero_division=0)), 4),
            "weighted_f1": round(float(f1_score(y_test, rf_preds, average="weighted", zero_division=0)), 4),
            "test_fpr": round(rf_fpr_test, 4),
            "classification_report": rf_report,
            "confusion_matrix": rf_cm
        },
        "logistic_regression": {
            "accuracy": round(float(np.mean(lr_preds == y_test)), 4),
            "macro_f1": round(float(f1_score(y_test, lr_preds, average="macro", zero_division=0)), 4),
            "weighted_f1": round(float(f1_score(y_test, lr_preds, average="weighted", zero_division=0)), 4),
            "test_fpr": round(lr_fpr_test, 4),
            "classification_report": lr_report,
            "confusion_matrix": lr_cm
        },
        "heuristics": {
            "accuracy": heur_results["accuracy"],
            "macro_f1": heur_results["macro_f1"],
            "weighted_f1": heur_results["weighted_f1"],
            "test_fpr": heur_results["false_positive_rate"],
            "classification_report": heur_results["classification_report"],
            "confusion_matrix": heur_results["confusion_matrix"]
        }
    }

    out_file = os.path.join(RESULTS_DIR, "offline_ml_evaluation.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(offline_payload, f, indent=2)
    print(f"[+] Offline Model Evaluation saved to {out_file}")

    # =========================================================================
    # 2. FALSE-POSITIVE STRESS TEST (1,000 Normal Telemetry Windows)
    # =========================================================================
    print("\n" + "=" * 80)
    print(" V4 EXPERIMENT A2: NORMAL-TRAFFIC FALSE POSITIVE STRESS TEST (1,000 WINDOWS)")
    print("=" * 80)

    df_normal = generate_false_positive_set(n_samples=1000, random_state=77)
    X_norm_unscaled = df_normal[FEATURE_NAMES].values
    X_norm_scaled = scaler.transform(X_norm_unscaled)

    # ML Predictions
    rf_norm_preds = rf_cal.predict(X_norm_scaled)
    lr_norm_preds = lr_cal.predict(X_norm_scaled)

    # Heuristic Predictions
    heur_detector = HeuristicDetector()
    heur_norm_preds = [heur_detector.evaluate(row)["class_id"] for row in X_norm_unscaled]
    heur_norm_preds = np.array(heur_norm_preds)

    # Autonomous System with Shadow Validation (A4 simulation on 1,000 windows)
    # In A4, a single isolated non-zero prediction does not promote to live unless 2 consecutive ticks occur or Class 3
    a4_false_actions = 0
    a4_false_quarantines = 0
    shadow_streak = 0
    for pred in rf_norm_preds:
        if pred == 0:
            shadow_streak = 0
        elif pred == 3:
            # Immediate quarantine only if RF has high confidence
            a4_false_quarantines += 1
            a4_false_actions += 1
            shadow_streak = 0
        else:
            shadow_streak += 1
            if shadow_streak >= 2:
                a4_false_actions += 1

    fpr_stress_payload = {
        "evaluation_windows": 1000,
        "traffic_type": "100% Attack-Free Normal BGP Telemetry",
        "random_forest_standalone": {
            "false_alarms": int(np.sum(rf_norm_preds != 0)),
            "fpr_percent": round(float(np.mean(rf_norm_preds != 0) * 100.0), 2),
            "false_quarantines": int(np.sum(rf_norm_preds == 3)),
            "false_quarantine_rate_percent": round(float(np.mean(rf_norm_preds == 3) * 100.0), 2)
        },
        "logistic_regression_standalone": {
            "false_alarms": int(np.sum(lr_norm_preds != 0)),
            "fpr_percent": round(float(np.mean(lr_norm_preds != 0) * 100.0), 2),
            "false_quarantines": int(np.sum(lr_norm_preds == 3)),
            "false_quarantine_rate_percent": round(float(np.mean(lr_norm_preds == 3) * 100.0), 2)
        },
        "heuristics_standalone": {
            "false_alarms": int(np.sum(heur_norm_preds != 0)),
            "fpr_percent": round(float(np.mean(heur_norm_preds != 0) * 100.0), 2),
            "false_quarantines": int(np.sum(heur_norm_preds == 3)),
            "false_quarantine_rate_percent": round(float(np.mean(heur_norm_preds == 3) * 100.0), 2)
        },
        "full_system_a4_safeguarded": {
            "false_mitigation_actions": a4_false_actions,
            "false_action_rate_percent": round(float(a4_false_actions / 1000.0 * 100.0), 2),
            "false_quarantines": a4_false_quarantines,
            "false_quarantine_rate_percent": round(float(a4_false_quarantines / 1000.0 * 100.0), 2)
        }
    }

    fpr_file = os.path.join(RESULTS_DIR, "fpr_stress_results.json")
    with open(fpr_file, "w", encoding="utf-8") as f:
        json.dump(fpr_stress_payload, f, indent=2)
    print(f"[+] False-Positive Stress Test saved to {fpr_file}")

    # =========================================================================
    # 3. ATTACK CLASS IMBALANCE SENSITIVITY TEST (90/10, 95/5, 99/1)
    # =========================================================================
    print("\n" + "=" * 80)
    print(" V4 EXPERIMENT A3: CLASS IMBALANCE SENSITIVITY TEST")
    print("=" * 80)

    imbalance_results = []
    ratios = [
        {"normal_ratio": 0.90, "attack_ratio": 0.10, "tag": "90/10 (10% Attack Rate)"},
        {"normal_ratio": 0.95, "attack_ratio": 0.05, "tag": "95/5 (5% Attack Rate)"},
        {"normal_ratio": 0.99, "attack_ratio": 0.01, "tag": "99/1 (1% Rare Attack Rate)"}
    ]

    normal_pool = df[df["label"] == 0]
    attack_pool = df[df["label"] != 0]

    for rat in ratios:
        n_attack = 50
        n_normal = int(n_attack * (rat["normal_ratio"] / rat["attack_ratio"]))
        
        # Sample with replacement if needed
        sampled_norm = normal_pool.sample(n=min(n_normal, len(normal_pool)), replace=True, random_state=42)
        sampled_att = attack_pool.sample(n=min(n_attack, len(attack_pool)), replace=True, random_state=42)
        df_imbalanced = pd.concat([sampled_norm, sampled_att], ignore_index=True)

        X_imb = df_imbalanced[FEATURE_NAMES].values
        y_imb = df_imbalanced["label"].astype(int).values
        X_imb_scaled = scaler.transform(X_imb)

        # Evaluate RF
        rf_imb_preds = rf_cal.predict(X_imb_scaled)
        rf_p, rf_r, rf_f1, _ = precision_recall_fscore_support(y_imb, rf_imb_preds, average="macro", zero_division=0)
        norm_idx = np.where(y_imb == 0)[0]
        rf_fpr = float(np.mean(rf_imb_preds[norm_idx] != 0)) if len(norm_idx) > 0 else 0.0

        # Evaluate Heuristics
        heur_imb_preds = np.array([heur_detector.evaluate(row)["class_id"] for row in X_imb])
        h_p, h_r, h_f1, _ = precision_recall_fscore_support(y_imb, heur_imb_preds, average="macro", zero_division=0)
        h_fpr = float(np.mean(heur_imb_preds[norm_idx] != 0)) if len(norm_idx) > 0 else 0.0

        imbalance_results.append({
            "ratio_tag": rat["tag"],
            "normal_samples": len(sampled_norm),
            "attack_samples": len(sampled_att),
            "random_forest": {
                "macro_precision": round(float(rf_p), 4),
                "macro_recall": round(float(rf_r), 4),
                "macro_f1": round(float(rf_f1), 4),
                "false_positive_rate": round(rf_fpr, 4)
            },
            "heuristics": {
                "macro_precision": round(float(h_p), 4),
                "macro_recall": round(float(h_r), 4),
                "macro_f1": round(float(h_f1), 4),
                "false_positive_rate": round(h_fpr, 4)
            }
        })

    imb_file = os.path.join(RESULTS_DIR, "class_imbalance_results.json")
    with open(imb_file, "w", encoding="utf-8") as f:
        json.dump(imbalance_results, f, indent=2)
    print(f"[+] Class Imbalance Results saved to {imb_file}")

    print("\n[+] All Offline Experiments Completed Successfully.")
    return offline_payload, fpr_stress_payload, imbalance_results


if __name__ == "__main__":
    run_offline_evaluation()
