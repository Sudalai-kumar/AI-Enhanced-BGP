"""
BGP Model Loader and Inference Engine with Schema Metadata Validation.
"""

import os
import json
import joblib
import numpy as np
from typing import Tuple, Dict, Any, Optional
from src.ai.feature_extractor import FEATURE_NAMES

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))

class SchemaMismatchError(Exception):
    """Raised when runtime feature schema does not match trained model metadata."""
    pass

class BGPClassifier:
    def __init__(self, model_type: str = "random_forest", models_dir: str = MODELS_DIR):
        self.model_type = model_type
        self.models_dir = models_dir
        self.scaler = None
        self.model = None
        self.metadata = {}
        self.load_models()

    def load_models(self):
        """Loads and strictly validates model schema against metadata artifact."""
        scaler_path = os.path.join(self.models_dir, "scaler.joblib")
        model_file = "random_forest.joblib" if self.model_type == "random_forest" else "logistic_regression.joblib"
        model_path = os.path.join(self.models_dir, model_file)
        meta_path = os.path.join(self.models_dir, "model_metadata.json")

        if not os.path.exists(scaler_path) or not os.path.exists(model_path):
            raise FileNotFoundError(f"Model artifacts missing in {self.models_dir}. Please run src/dataset/train_models.py.")

        # Load Metadata Artifact
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
            
            # Validate Schema Integrity
            expected_features = self.metadata.get("feature_names", [])
            if expected_features != FEATURE_NAMES:
                raise SchemaMismatchError(
                    f"Feature mismatch! Model expects {expected_features}, but runtime has {FEATURE_NAMES}"
                )

        self.scaler = joblib.load(scaler_path)
        self.model = joblib.load(model_path)

        # Validate Scaler Dimension
        if getattr(self.scaler, "n_features_in_", 10) != len(FEATURE_NAMES):
            raise SchemaMismatchError(
                f"Scaler feature count mismatch: expected {len(FEATURE_NAMES)}, got {self.scaler.n_features_in_}"
            )

    def predict(self, feature_vector: np.ndarray) -> Tuple[int, np.ndarray]:
        """
        Executes calibrated inference on a single 10-element feature vector.
        Returns: (predicted_class_id, calibrated_probability_array)
        """
        vec = np.asarray(feature_vector, dtype=np.float32).reshape(1, -1)
        if vec.shape[1] != len(FEATURE_NAMES):
            raise ValueError(f"Feature vector must have length {len(FEATURE_NAMES)}, got {vec.shape[1]}")

        vec_scaled = self.scaler.transform(vec)
        probs = self.model.predict_proba(vec_scaled)[0]
        pred_class = int(np.argmax(probs))
        return pred_class, probs
