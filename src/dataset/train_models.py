"""
Standardized BGP Machine Learning Dataset Training & Evaluation Pipeline.
Calibrates classifiers using stratified 5-fold cross-validation,
saves models/metadata, and automatically updates experiments/results/model_training_evaluation.json.

Holdout strategy: cross-seed holdout.
  - Training data generated with random_state=42.
  - Test data generated with random_state=99 (different seed, same generator).
  This prevents any within-generator correlation between train and test splits
  while remaining fully reproducible.  It does NOT claim temporal ordering.
"""

import os
import sys
import json
import hashlib
import subprocess
import datetime
import joblib
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import classification_report, f1_score, confusion_matrix

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.dataset.generator import generate_bgp_dataset, generate_false_positive_set, FEATURE_NAMES

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))
RESULTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "experiments", "results"))

TARGET_NAMES = ["Normal", "Suspicious", "Route Leak Candidate", "Prefix Hijack Candidate"]


def _sha256_file(path: str) -> str:
    """Returns hex SHA-256 digest of a file, or 'file-not-found' if missing."""
    if not os.path.exists(path):
        return "file-not-found"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_dataframe(df) -> str:
    """Returns hex SHA-256 digest of a DataFrame serialized to CSV bytes."""
    raw = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _git_commit() -> str:
    """Returns the current git commit SHA, or 'unknown' if git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def train_and_save_models(n_samples: int = 15000,
                          train_seed: int = 42,
                          test_seed: int = 99):
    """
    Trains and evaluates Random Forest and Logistic Regression classifiers.

    Uses a cross-seed holdout: training data is generated with train_seed,
    test data is independently generated with test_seed.  This strategy avoids
    within-generator correlation and is documented as 'cross_seed_holdout'.
    """
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print(f"[*] Generating {n_samples} training samples (seed={train_seed})...")
    print(f"[*] Generating {n_samples} test samples (seed={test_seed}) [cross-seed holdout]...")

    df_train_full = generate_bgp_dataset(n_samples=n_samples, random_state=train_seed)
    df_test_full = generate_bgp_dataset(n_samples=n_samples, random_state=test_seed)

    # Compute dataset hashes before splitting (for reproducibility manifest)
    train_dataset_sha256 = _sha256_dataframe(df_train_full)
    test_dataset_sha256 = _sha256_dataframe(df_test_full)

    feature_cols = FEATURE_NAMES
    X_train = df_train_full[feature_cols].values
    y_train = df_train_full["label"].values
    X_test = df_test_full[feature_cols].values
    y_test = df_test_full["label"].values

    print(f"[+] Train size: {len(X_train)}, Test size: {len(X_test)}")

    # Fit Scaler strictly on training data
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # ------------------------------------------------------------------
    # 1. Train & Calibrate Random Forest
    # ------------------------------------------------------------------
    rf_base = RandomForestClassifier(
        n_estimators=50,
        max_depth=12,
        class_weight="balanced",
        random_state=train_seed,
        n_jobs=1
    )
    rf_calibrated = CalibratedClassifierCV(estimator=rf_base, cv=5, method="isotonic")
    rf_calibrated.fit(X_train_scaled, y_train)

    # Fit base model separately to extract feature importances
    rf_base.fit(X_train_scaled, y_train)
    feature_importances = {
        name: round(float(imp), 4)
        for name, imp in zip(FEATURE_NAMES, rf_base.feature_importances_)
    }

    # ------------------------------------------------------------------
    # 2. Train & Calibrate Logistic Regression
    # ------------------------------------------------------------------
    lr_base = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=train_seed
    )
    lr_calibrated = CalibratedClassifierCV(estimator=lr_base, cv=5, method="sigmoid")
    lr_calibrated.fit(X_train_scaled, y_train)

    # ------------------------------------------------------------------
    # 3. Evaluate on cross-seed test set
    # ------------------------------------------------------------------
    rf_preds = rf_calibrated.predict(X_test_scaled)
    lr_preds = lr_calibrated.predict(X_test_scaled)

    rf_report = classification_report(y_test, rf_preds, target_names=TARGET_NAMES, output_dict=True)
    lr_report = classification_report(y_test, lr_preds, target_names=TARGET_NAMES, output_dict=True)

    rf_cm = confusion_matrix(y_test, rf_preds, labels=[0, 1, 2, 3]).tolist()
    lr_cm = confusion_matrix(y_test, lr_preds, labels=[0, 1, 2, 3]).tolist()

    rf_f1_macro = float(f1_score(y_test, rf_preds, average="macro"))
    rf_f1_weighted = float(f1_score(y_test, rf_preds, average="weighted"))
    lr_f1_macro = float(f1_score(y_test, lr_preds, average="macro"))
    lr_f1_weighted = float(f1_score(y_test, lr_preds, average="weighted"))

    print(f"[+] Cross-seed Test F1 (macro): RF={rf_f1_macro:.4f} | LR={lr_f1_macro:.4f}")
    print(f"[+] Cross-seed Test F1 (weighted): RF={rf_f1_weighted:.4f} | LR={lr_f1_weighted:.4f}")

    # ------------------------------------------------------------------
    # 4. False-positive rate on challenge set
    # ------------------------------------------------------------------
    print("[*] Evaluating false-positive rate on challenge set (seed=77)...")
    df_fp = generate_false_positive_set(n_samples=1000, random_state=77)
    X_fp = scaler.transform(df_fp[feature_cols].values)
    y_fp_true = df_fp["label"].values  # all 0 (Normal)

    rf_fp_preds = rf_calibrated.predict(X_fp)
    lr_fp_preds = lr_calibrated.predict(X_fp)

    rf_fpr = float(np.mean(rf_fp_preds != 0))
    lr_fpr = float(np.mean(lr_fp_preds != 0))
    print(f"[+] False Positive Rate: RF={rf_fpr:.4f} | LR={lr_fpr:.4f}")

    # ------------------------------------------------------------------
    # 5. Persist models, scaler, and metadata
    # ------------------------------------------------------------------
    scaler_path = os.path.join(MODELS_DIR, "scaler.joblib")
    rf_path = os.path.join(MODELS_DIR, "random_forest.joblib")
    lr_path = os.path.join(MODELS_DIR, "logistic_regression.joblib")

    joblib.dump(scaler, scaler_path)
    joblib.dump(rf_calibrated, rf_path)
    joblib.dump(lr_calibrated, lr_path)

    rf_sha256 = _sha256_file(rf_path)
    lr_sha256 = _sha256_file(lr_path)
    git_commit = _git_commit()
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"

    metadata = {
        "model_version": "bgp-v3.0-calibrated-overlapping",
        "training_timestamp": timestamp,
        "git_commit": git_commit,
        "evaluation_method": "cross_seed_holdout",
        "evaluation_method_note": (
            "Training and test sets are generated independently using different random seeds "
            "(train_seed=42, test_seed=99). This prevents within-generator correlation. "
            "This is NOT a temporal holdout and does not claim temporal ordering."
        ),
        "train_seed": train_seed,
        "test_seed": test_seed,
        "feature_count": len(FEATURE_NAMES),
        "feature_names": FEATURE_NAMES,
        "sample_counts": {
            "train": len(X_train),
            "test": len(X_test),
            "false_positive_challenge": len(X_fp)
        },
        "dataset_sha256": {
            "train": train_dataset_sha256,
            "test": test_dataset_sha256
        },
        "models": {
            "random_forest": {
                "algorithm": "RandomForestClassifier (50 estimators, max_depth=12)",
                "calibration": "CalibratedClassifierCV (5-fold, isotonic)",
                "test_macro_f1": round(rf_f1_macro, 4),
                "test_weighted_f1": round(rf_f1_weighted, 4),
                "false_positive_rate": round(rf_fpr, 4),
                "model_sha256": rf_sha256
            },
            "logistic_regression": {
                "algorithm": "LogisticRegression (max_iter=1000, balanced)",
                "calibration": "CalibratedClassifierCV (5-fold, sigmoid)",
                "test_macro_f1": round(lr_f1_macro, 4),
                "test_weighted_f1": round(lr_f1_weighted, 4),
                "false_positive_rate": round(lr_fpr, 4),
                "model_sha256": lr_sha256
            }
        }
    }

    with open(os.path.join(MODELS_DIR, "model_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # ------------------------------------------------------------------
    # 6. Save detailed evaluation report
    # ------------------------------------------------------------------
    eval_results = {
        "evaluation_method": "cross_seed_holdout",
        "evaluation_method_note": metadata["evaluation_method_note"],
        "training_timestamp": timestamp,
        "git_commit": git_commit,
        "dataset_summary": {
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "false_positive_challenge_samples": len(X_fp),
            "features": FEATURE_NAMES,
            "dataset_sha256": {
                "train": train_dataset_sha256,
                "test": test_dataset_sha256
            }
        },
        "random_forest": {
            "macro_f1": round(rf_f1_macro, 4),
            "weighted_f1": round(rf_f1_weighted, 4),
            "false_positive_rate": round(rf_fpr, 4),
            "feature_importances": feature_importances,
            "classification_report": rf_report,
            "confusion_matrix": rf_cm,
            "model_sha256": rf_sha256
        },
        "logistic_regression": {
            "macro_f1": round(lr_f1_macro, 4),
            "weighted_f1": round(lr_f1_weighted, 4),
            "false_positive_rate": round(lr_fpr, 4),
            "classification_report": lr_report,
            "confusion_matrix": lr_cm,
            "model_sha256": lr_sha256
        }
    }

    eval_json_path = os.path.join(RESULTS_DIR, "model_training_evaluation.json")
    with open(eval_json_path, "w", encoding="utf-8") as f:
        json.dump(eval_results, f, indent=2)

    print(f"[+] Artifacts persisted:\n  - {MODELS_DIR}/\n  - {eval_json_path}")


train_and_evaluate = train_and_save_models

if __name__ == "__main__":
    train_and_save_models()
