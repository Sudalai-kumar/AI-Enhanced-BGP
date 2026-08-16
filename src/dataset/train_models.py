"""
ML Model Training Pipeline with Stratified 70/15/15 Data Splitting and Scaler Serialization.
Trains:
1. Random Forest (Class Weight = Balanced, 100 Estimators)
2. Logistic Regression (Class Weight = Balanced, Max Iter = 1000)
Exports serialized models, scaler, and evaluation performance metrics.
"""

import os
import sys
import json
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score, precision_score, recall_score, confusion_matrix

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.dataset.generator import generate_bgp_dataset, FEATURE_NAMES, CLASS_NAMES
from src.utils.logger import setup_logger

logger = setup_logger("train_models")

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))
RESULTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "experiments", "results"))

def train_and_evaluate(n_samples: int = 15000, random_state: int = 42):
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    logger.info(f"Generating synthetic dataset with {n_samples} samples...")
    df = generate_bgp_dataset(n_samples=n_samples, random_state=random_state)
    
    X = df[FEATURE_NAMES].values
    y = df["label"].values
    
    # 1. Stratified 70% Train, 15% Validation, 15% Test Split
    logger.info("Performing Stratified 70/15/15 Split...")
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.30, stratify=y, random_state=random_state
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.50, stratify=y_temp, random_state=random_state
    )
    
    logger.info(f"Dataset split: Train={len(X_train)}, Val={len(X_val)}, Test={len(X_test)}")
    
    # 2. Fit StandardScaler strictly on Train partition
    logger.info("Fitting StandardScaler on Train set...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)
    
    scaler_path = os.path.join(MODELS_DIR, "scaler.joblib")
    joblib.dump(scaler, scaler_path)
    logger.info(f"Fitted scaler saved to {scaler_path}")
    
    # 3. Train Random Forest Classifier
    logger.info("Training Random Forest Classifier (class_weight='balanced')...")
    rf_model = RandomForestClassifier(
        n_estimators=50,
        max_depth=10,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=1
    )
    rf_model.fit(X_train_scaled, y_train)
    rf_path = os.path.join(MODELS_DIR, "random_forest.joblib")
    joblib.dump(rf_model, rf_path)
    
    # 4. Train Logistic Regression Classifier
    logger.info("Training Logistic Regression Baseline (class_weight='balanced')...")
    lr_model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=random_state
    )
    lr_model.fit(X_train_scaled, y_train)
    lr_path = os.path.join(MODELS_DIR, "logistic_regression.joblib")
    joblib.dump(lr_model, lr_path)
    
    # 5. Evaluate on Independent Test Set
    logger.info("Evaluating models on Test Set (15%)...")
    rf_preds = rf_model.predict(X_test_scaled)
    lr_preds = lr_model.predict(X_test_scaled)
    
    target_names = [CLASS_NAMES[i] for i in sorted(CLASS_NAMES.keys())]
    
    rf_report = classification_report(y_test, rf_preds, target_names=target_names, output_dict=True)
    lr_report = classification_report(y_test, lr_preds, target_names=target_names, output_dict=True)
    
    # Feature Importances (Random Forest)
    importances = dict(zip(FEATURE_NAMES, [round(float(x), 4) for x in rf_model.feature_importances_]))
    sorted_importances = dict(sorted(importances.items(), key=lambda item: item[1], reverse=True))
    
    results = {
        "dataset_summary": {
            "total_samples": n_samples,
            "train_samples": len(X_train),
            "val_samples": len(X_val),
            "test_samples": len(X_test),
            "features": FEATURE_NAMES
        },
        "random_forest": {
            "macro_f1": round(f1_score(y_test, rf_preds, average="macro"), 4),
            "weighted_f1": round(f1_score(y_test, rf_preds, average="weighted"), 4),
            "feature_importances": sorted_importances,
            "classification_report": rf_report,
            "confusion_matrix": confusion_matrix(y_test, rf_preds).tolist()
        },
        "logistic_regression": {
            "macro_f1": round(f1_score(y_test, lr_preds, average="macro"), 4),
            "weighted_f1": round(f1_score(y_test, lr_preds, average="weighted"), 4),
            "classification_report": lr_report,
            "confusion_matrix": confusion_matrix(y_test, lr_preds).tolist()
        }
    }
    
    out_json = os.path.join(RESULTS_DIR, "model_training_evaluation.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    logger.info(f"Model evaluation report saved to {out_json}")
    
    print("\n" + "=" * 65)
    print(f" RANDOM FOREST TEST REPORT (Macro F1: {results['random_forest']['macro_f1']})")
    print("=" * 65)
    print(classification_report(y_test, rf_preds, target_names=target_names))
    
    print("\n" + "=" * 65)
    print(f" LOGISTIC REGRESSION TEST REPORT (Macro F1: {results['logistic_regression']['macro_f1']})")
    print("=" * 65)
    print(classification_report(y_test, lr_preds, target_names=target_names))
    
    print("\n[+] Top 5 Discriminative Features (Random Forest Importance):")
    for feat, imp in list(sorted_importances.items())[:5]:
        print(f"  - {feat}: {imp * 100:.2f}%")
        
    return results

if __name__ == "__main__":
    train_and_evaluate()
