"""
CLI Script to train and evaluate AI Classifiers (Random Forest & Logistic Regression).
Generates synthetic BGP dataset with overlapping distributions and evaluates on cross-seed holdout.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.dataset.train_models import train_and_save_models, train_from_real_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train and evaluate BGP AI Classifiers")
    parser.add_argument("--real-data", action="store_true", help="Train on empirical testbed dataset (bgp_real_training.jsonl)")
    parser.add_argument("--dataset", default=None, help="Explicit path to JSONL training dataset")
    parser.add_argument("--samples", type=int, default=15000, help="Number of synthetic samples (if not using --real-data)")
    parser.add_argument("--train-seed", type=int, default=42, help="Random seed for training split")
    parser.add_argument("--test-seed", type=int, default=99, help="Random seed for test split")
    args = parser.parse_args()

    if args.real_data or args.dataset:
        print("[*] Training mode: EMPIRICAL (live testbed data)")
        train_from_real_data(jsonl_path=args.dataset)
    else:
        print("[*] Training mode: SYNTHETIC (parameterized generator)")
        train_and_save_models(n_samples=args.samples, train_seed=args.train_seed, test_seed=args.test_seed)
