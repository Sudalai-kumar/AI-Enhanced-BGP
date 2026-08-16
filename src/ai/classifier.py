"""
ML Model Wrapper and Inference Engine.
Loads serialized models and pre-fitted scaler, providing batch and single-route predictions.
"""

import os
import joblib
import numpy as np
from typing import Dict, Any, Tuple, Optional

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))

class BGPClassifier:
    def __init__(self, model_type: str = "random_forest"):
        self.model_type = model_type
        self.scaler = None
        self.model = None
        self._load_artifacts()

    def _load_artifacts(self):
        scaler_path = os.path.join(MODELS_DIR, "scaler.joblib")
        if not os.path.exists(scaler_path):
            raise FileNotFoundError(f"Scaler not found at {scaler_path}. Run train_models.py first.")
        self.scaler = joblib.load(scaler_path)

        model_filename = f"{self.model_type}.joblib"
        model_path = os.path.join(MODELS_DIR, model_filename)
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found at {model_path}. Run train_models.py first.")
        self.model = joblib.load(model_path)

    def predict(self, feature_vector: np.ndarray) -> Tuple[int, np.ndarray]:
        """
        Scales input feature vector using saved scaler and performs inference.
        Returns: (predicted_class_id, class_probabilities_array)
        """
        if feature_vector.ndim == 1:
            X = feature_vector.reshape(1, -1)
        else:
            X = feature_vector
            
        X_scaled = self.scaler.transform(X)
        pred_class = int(self.model.predict(X_scaled)[0])
        probabilities = self.model.predict_proba(X_scaled)[0]
        return pred_class, probabilities
