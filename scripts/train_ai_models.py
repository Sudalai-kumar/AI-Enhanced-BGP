"""
CLI Script to train and evaluate AI Classifiers (Random Forest & Logistic Regression).
Generates synthetic BGP dataset with overlapping distributions and evaluates on cross-seed holdout.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.dataset.train_models import train_and_save_models

if __name__ == "__main__":
    train_and_save_models(n_samples=15000, train_seed=42, test_seed=99)
