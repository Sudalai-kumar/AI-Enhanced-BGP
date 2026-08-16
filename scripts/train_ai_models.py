"""
CLI Script to train and evaluate AI Classifiers (Random Forest & Logistic Regression).
Generates synthetic BGP dataset, fits models with 70/15/15 stratified split,
and exports metrics and model artifacts.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.dataset.train_models import train_and_evaluate

if __name__ == "__main__":
    train_and_evaluate(n_samples=15000, random_state=42)
