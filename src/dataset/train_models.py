"""
Standardized BGP Machine Learning Dataset Training Pipeline.
Calibrates classifiers using explicit stratified 5-fold cross-validation
and generates complete, per-model metadata artifacts.
"""

import os
import sys
import json
import joblib
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import classification_report, f1_score

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.dataset.generator import generate_bgp_dataset, FEATURE_NAMES

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))
RESULTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "experiments", "results"))

def train_and_save_models(n_samples: int = 10000, random_state: int = 42):
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print(f"[*] Generating {n_samples} synthetic BGP telemetry samples...")

    df = generate_bgp_dataset(n_samples=n_samples, random_state=random_state)

    feature_cols = FEATURE_NAMES
    X = df[feature_cols].values
    y = df["label"].values

    # Stratified Train (70%), Validation (15%), Test (15%) splits
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=0.15, random_state=random_state, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_val, y_train_val, test_size=0.1765, random_state=random_state, stratify=y_train_val
    )

    print(f"[+] Splits: Train={len(X_train)}, Val={len(X_val)}, Test={len(X_test)}")

    # Fit Scaler strictly on Training split
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)

    # 1. Train & Calibrate Random Forest with 5-Fold Cross Validation
    rf_base = RandomForestClassifier(
        n_estimators=50,
        max_depth=12,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=1
    )
    rf_calibrated = CalibratedClassifierCV(estimator=rf_base, cv=5, method="isotonic")
    rf_calibrated.fit(X_train_scaled, y_train)

    # 2. Train & Calibrate Logistic Regression with 5-Fold Cross Validation
    lr_base = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=random_state
    )
    lr_calibrated = CalibratedClassifierCV(estimator=lr_base, cv=5, method="sigmoid")
    lr_calibrated.fit(X_train_scaled, y_train)

    # Evaluate on Test Split
    rf_preds = rf_calibrated.predict(X_test_scaled)
    lr_preds = lr_calibrated.predict(X_test_scaled)

    rf_f1_macro = float(f1_score(y_test, rf_preds, average="macro"))
    rf_f1_weighted = float(f1_score(y_test, rf_preds, average="weighted"))
    lr_f1_macro = float(f1_score(y_test, lr_preds, average="macro"))
    lr_f1_weighted = float(f1_score(y_test, lr_preds, average="weighted"))

    print(f"[+] Calibrated Test F1: RF={rf_f1_weighted:.4f} | LR={lr_f1_weighted:.4f}")

    # Persist Models & Scaler
    joblib.dump(scaler, os.path.join(MODELS_DIR, "scaler.joblib"))
    joblib.dump(rf_calibrated, os.path.join(MODELS_DIR, "random_forest.joblib"))
    joblib.dump(lr_calibrated, os.path.join(MODELS_DIR, "logistic_regression.joblib"))

    # Save comprehensive metadata covering both estimators
    metadata = {
        "model_version": "bgp-v2.0-calibrated",
        "training_timestamp": "2026-08-18",
        "feature_count": len(FEATURE_NAMES),
        "feature_names": FEATURE_NAMES,
        "sample_counts": {
            "total": n_samples,
            "train": len(X_train),
            "val": len(X_val),
            "test": len(X_test)
        },
        "models": {
            "random_forest": {
                "algorithm": "RandomForestClassifier (50 estimators, max_depth=12)",
                "calibration": "CalibratedClassifierCV (5-fold, isotonic)",
                "test_macro_f1": round(rf_f1_macro, 4),
                "test_weighted_f1": round(rf_f1_weighted, 4)
            },
            "logistic_regression": {
                "algorithm": "LogisticRegression (max_iter=1000, balanced)",
                "calibration": "CalibratedClassifierCV (5-fold, sigmoid)",
                "test_macro_f1": round(lr_f1_macro, 4),
                "test_weighted_f1": round(lr_f1_weighted, 4)
            }
        }
    }

    with open(os.path.join(MODELS_DIR, "model_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"[+] Artifacts successfully persisted to {MODELS_DIR}/")

if __name__ == "__main__":
    train_and_save_models()
