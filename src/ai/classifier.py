"""
Standardized BGP Machine Learning Classifier Loader and Real-Time Predictor.
Enforces strict schema validation against model_metadata.json.
"""

import os
import sys
import json
import joblib
import numpy as np
from typing import Tuple, Optional

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))
SCALER_PATH = os.path.join(MODELS_DIR, "scaler.joblib")
RF_MODEL_PATH = os.path.join(MODELS_DIR, "random_forest.joblib")
LR_MODEL_PATH = os.path.join(MODELS_DIR, "logistic_regression.joblib")
METADATA_PATH = os.path.join(MODELS_DIR, "model_metadata.json")

class BGPClassifier:
    def __init__(self, model_type: str = "random_forest"):
        self.model_type = model_type
        self.scaler = None
        self.model = None
        self.metadata = None
        self.load_models()

    def load_models(self):
        """Loads models and strictly enforces schema metadata."""
        if not os.path.exists(SCALER_PATH):
            raise FileNotFoundError(f"Scaler not found at {SCALER_PATH}. Run train_models.py first.")
        
        # Strict Metadata Requirement
        if not os.path.exists(METADATA_PATH):
            raise FileNotFoundError(f"Model metadata schema missing at {METADATA_PATH}. Required for schema safety.")

        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        self.scaler = joblib.load(SCALER_PATH)

        if self.model_type == "random_forest":
            if not os.path.exists(RF_MODEL_PATH):
                raise FileNotFoundError(f"Random Forest model not found at {RF_MODEL_PATH}.")
            self.model = joblib.load(RF_MODEL_PATH)
        elif self.model_type == "logistic_regression":
            if not os.path.exists(LR_MODEL_PATH):
                raise FileNotFoundError(f"Logistic Regression model not found at {LR_MODEL_PATH}.")
            self.model = joblib.load(LR_MODEL_PATH)
        else:
            raise ValueError(f"Unknown model_type: {self.model_type}")

    def predict(self, feature_vector: np.ndarray) -> Tuple[int, np.ndarray]:
        """
        Runs calibrated inference on single 10-feature vector.
        Returns: (predicted_class_id, calibrated_probabilities)
        """
        # Strict vector shape assertion
        expected_len = self.metadata.get("feature_count", 10)
        if len(feature_vector) != expected_len:
            raise ValueError(f"Feature vector shape mismatch: got {len(feature_vector)}, expected {expected_len}.")

        # Scale input
        x_scaled = self.scaler.transform(feature_vector.reshape(1, -1))
        
        # Predict calibrated class probabilities
        probs = self.model.predict_proba(x_scaled)[0]
        pred_class = int(np.argmax(probs))
        
        return pred_class, probs
