"""
ML Model Training and Calibration Pipeline.
Trains Random Forest and Logistic Regression with:
- 70/15/15 Stratified Split
- Model Calibration via CalibratedClassifierCV on validation split
- Saves model metadata schema artifact (model_metadata.json)
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
from src.dataset.generator import generate_bgp_dataset
from src.ai.feature_extractor import FEATURE_NAMES

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

    # 70% Train, 15% Validation, 15% Test (Stratified)
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.30, random_state=random_state, stratify=y
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.50, random_state=random_state, stratify=y_temp
    )

    print(f"[+] Splits: Train={len(X_train)}, Val={len(X_val)}, Test={len(X_test)}")

    # Fit Scaler ONLY on Training Split
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)

    # 1. Train Base Random Forest with 5-fold Calibration
    rf_base = RandomForestClassifier(
        n_estimators=50,
        max_depth=12,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=1
    )
    rf_calibrated = CalibratedClassifierCV(estimator=rf_base, cv=5, method="isotonic")
    rf_calibrated.fit(X_train_scaled, y_train)

    # 2. Train Base Logistic Regression with 5-fold Calibration
    lr_base = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=random_state
    )
    lr_calibrated = CalibratedClassifierCV(estimator=lr_base, cv=5, method="sigmoid")
    lr_calibrated.fit(X_train_scaled, y_train)

    # Evaluate on Unseen Test Set
    rf_preds = rf_calibrated.predict(X_test_scaled)
    lr_preds = lr_calibrated.predict(X_test_scaled)

    rf_f1 = f1_score(y_test, rf_preds, average="weighted")
    lr_f1 = f1_score(y_test, lr_preds, average="weighted")
    print(f"[+] Calibrated Test F1-Score: Random Forest = {rf_f1:.4f} | Logistic Regression = {lr_f1:.4f}")

    # Save Models and Scaler
    scaler_path = os.path.join(MODELS_DIR, "scaler.joblib")
    rf_path = os.path.join(MODELS_DIR, "random_forest.joblib")
    lr_path = os.path.join(MODELS_DIR, "logistic_regression.joblib")

    joblib.dump(scaler, scaler_path)
    joblib.dump(rf_calibrated, rf_path)
    joblib.dump(lr_calibrated, lr_path)

    # Save Model Schema Metadata Artifact
    metadata = {
        "model_version": "rf-v2.0-calibrated",
        "feature_version": "v2",
        "feature_names": feature_cols,
        "n_features": len(feature_cols),
        "n_estimators": 50,
        "training_samples": len(X_train),
        "validation_samples": len(X_val),
        "test_samples": len(X_test),
        "calibrated": True,
        "calibration_method": "isotonic",
        "training_seed": random_state,
        "test_macro_f1": float(f1_score(y_test, rf_preds, average="macro")),
        "test_weighted_f1": float(rf_f1)
    }
    meta_path = os.path.join(MODELS_DIR, "model_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"[+] Artifacts successfully persisted to {MODELS_DIR}/")

if __name__ == "__main__":
    train_and_save_models()
