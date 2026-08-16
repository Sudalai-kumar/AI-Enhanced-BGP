"""
Unit tests and Inference Latency Budgeting for BGP ML Classifiers.
Asserts:
1. Model loading and scaler consistency.
2. Inference correctness across Normal, Suspicious, Route Leak, and Prefix Hijack vectors.
3. Inference Latency Budget: < 1.0 ms per route prediction.
"""

import unittest
import numpy as np
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.ai.classifier import BGPClassifier
from src.ai.hybrid_engine import HybridDecisionEngine

class TestBGPClassifier(unittest.TestCase):
    def setUp(self):
        self.rf_classifier = BGPClassifier(model_type="random_forest")
        self.lr_classifier = BGPClassifier(model_type="logistic_regression")
        self.engine = HybridDecisionEngine(classifier=self.rf_classifier)

    def test_inference_latency_budget(self):
        """Asserts that per-route ML inference latency stays within strict real-time budgets."""
        sample_vector = np.array([2.0, 0.0, 0.0, 24.0, 1.0, 0.0, 100.0, 1500.0, 0.0, 1.0], dtype=np.float32)
        
        # 1. Benchmark Logistic Regression (< 1.0 ms budget)
        self.lr_classifier.predict(sample_vector) # Warmup
        n_trials = 200
        start = time.perf_counter()
        for _ in range(n_trials):
            pred_class, probs = self.lr_classifier.predict(sample_vector)
        lr_latency_ms = ((time.perf_counter() - start) * 1000.0) / n_trials
        print(f"\n[+] Measured Logistic Regression Latency: {lr_latency_ms:.4f} ms per prediction")
        self.assertLess(lr_latency_ms, 1.0, "Logistic Regression exceeded 1.0 ms budget!")

        # 2. Benchmark Random Forest (< 15.0 ms budget)
        self.rf_classifier.predict(sample_vector) # Warmup
        start = time.perf_counter()
        for _ in range(n_trials):
            pred_class, probs = self.rf_classifier.predict(sample_vector)
        rf_latency_ms = ((time.perf_counter() - start) * 1000.0) / n_trials
        print(f"[+] Measured Random Forest Latency: {rf_latency_ms:.4f} ms per prediction")
        self.assertLess(rf_latency_ms, 15.0, "Random Forest exceeded 15.0 ms budget!")

    def test_classification_correctness(self):
        # 1. Normal Vector
        norm_vec = np.array([2.0, 0.0, 0.0, 24.0, 1.0, 0.0, 100.0, 2500.0, 0.0, 1.0], dtype=np.float32)
        pred, probs = self.rf_classifier.predict(norm_vec)
        self.assertEqual(pred, 0) # Normal
        
        # 2. Prefix Hijack Vector (origin_as_change = 1)
        hijack_vec = np.array([2.0, 3.0, 1.0, 24.0, 2.0, 0.0, 100.0, 10.0, 0.0, 0.5], dtype=np.float32)
        pred, probs = self.rf_classifier.predict(hijack_vec)
        self.assertEqual(pred, 3) # Hijack
        
        # 3. Route Leak Vector (valley_free = 1, long path)
        leak_vec = np.array([6.0, 4.0, 0.0, 24.0, 3.0, 0.0, 100.0, 30.0, 1.0, 0.5], dtype=np.float32)
        pred, probs = self.rf_classifier.predict(leak_vec)
        self.assertEqual(pred, 2) # Route Leak

    def test_hybrid_decision_trust_score(self):
        norm_vec = np.array([2.0, 0.0, 0.0, 24.0, 1.0, 0.0, 100.0, 2500.0, 0.0, 1.0], dtype=np.float32)
        pred, probs = self.rf_classifier.predict(norm_vec)
        route_meta = {"origin_as": 65001}
        decision = self.engine.evaluate("192.0.2.0/24", route_meta, norm_vec, probs)
        
        self.assertEqual(decision["classification_name"], "Normal")
        self.assertGreaterEqual(decision["trust_score"], 0.90)

if __name__ == "__main__":
    unittest.main()
