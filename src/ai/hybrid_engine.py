"""
Hybrid Decision & Multi-Factor Behavioral Trust Scoring Engine.
Calculates a continuous behavioral trust score based on 6 weighted indicators:
- Origin stability (20%)
- AS-Path valley-free adherence & edit distance (20%)
- 5-minute flap quiescence (15%)
- Prefix specificity & deaggregation (15%)
- Neighbor diversity & peer availability (10%)
- Calibrated ML Model Trust (20%)
"""

import numpy as np
from typing import Dict, Any, List, Optional
from src.ai.classifier import BGPClassifier

CLASS_NAMES = {
    0: "Normal",
    1: "Suspicious",
    2: "Route Leak Candidate",
    3: "Prefix Hijack Candidate"
}

class HybridDecisionEngine:
    def __init__(self, classifier: Optional[BGPClassifier] = None):
        self.classifier = classifier or BGPClassifier()
        # Explicit Indicator Weights summing to 1.0
        self.weights = {
            "origin": 0.20,
            "path": 0.20,
            "flap": 0.15,
            "prefix": 0.15,
            "peer": 0.10,
            "ml": 0.20
        }

    def compute_behavioral_trust(self, feature_vector: np.ndarray, ml_prob_normal: float) -> float:
        """
        Computes the weighted multi-factor behavioral trust score in [0.0, 1.0].
        Feature indices:
        0: as_path_len, 1: as_path_edit_distance, 2: origin_as_change,
        3: prefix_mask_len, 4: announcements_per_minute, 5: flap_count_5min,
        6: loc_pref_current, 7: route_age_seconds, 8: valley_free_violation,
        9: neighbor_diversity
        """
        origin_change = feature_vector[2]
        mask_len = feature_vector[3]
        flap_count = feature_vector[5]
        valley_free = feature_vector[8]
        edit_dist = feature_vector[1]
        neighbor_div = feature_vector[9]

        # 1. Origin Stability: 0.0 if origin changed, else 1.0
        t_origin = 0.0 if origin_change > 0.5 else 1.0

        # 2. Path Stability: Penalized by valley-free violation and edit distance
        t_path = 0.0 if valley_free > 0.5 else max(0.0, 1.0 - (edit_dist * 0.2))

        # 3. Flap Quiescence: Decays with recent flaps
        t_flap = max(0.0, 1.0 - (flap_count / 5.0))

        # 4. Prefix Legitimacy: Sub-prefix deaggregation (> /24) penalized
        t_prefix = 0.4 if mask_len > 24.0 else 1.0

        # 5. Peer Consistency
        t_peer = float(neighbor_div)

        # 6. ML Model Confidence
        t_ml = float(ml_prob_normal)

        trust = (
            self.weights["origin"] * t_origin +
            self.weights["path"] * t_path +
            self.weights["flap"] * t_flap +
            self.weights["prefix"] * t_prefix +
            self.weights["peer"] * t_peer +
            self.weights["ml"] * t_ml
        )

        return float(np.clip(trust, 0.0, 1.0))

    def evaluate(self, prefix: str, current_route: Dict[str, Any],
                 feature_vector: np.ndarray, raw_probabilities: np.ndarray) -> Dict[str, Any]:
        """
        Produces explainable decision with multi-factor trust score and reason tags.
        """
        predicted_class_id = int(np.argmax(raw_probabilities))
        confidence = float(np.max(raw_probabilities))
        prob_normal = float(raw_probabilities[0])

        trust_score = self.compute_behavioral_trust(feature_vector, prob_normal)

        # Generate Explainable Diagnostic Reasons
        reasons: List[str] = []
        if feature_vector[2] > 0.5:
            reasons.append(f"Origin AS mismatch (origin_as_change=1, current_origin={current_route.get('origin_as')})")
        if feature_vector[8] > 0.5:
            reasons.append(f"Gao-Rexford valley-free violation detected in AS-path: {current_route.get('as_path')}")
        if feature_vector[3] > 24.0:
            reasons.append(f"Sub-prefix deaggregation detected (/{int(feature_vector[3])} > /24)")
        if feature_vector[5] >= 3.0:
            reasons.append(f"High route churn ({int(feature_vector[5])} flaps in 5min)")
        if feature_vector[1] >= 2.0 and feature_vector[8] <= 0.5:
            reasons.append(f"Significant AS-path edit distance ({int(feature_vector[1])} edits vs baseline)")

        if not reasons:
            reasons.append("All behavioral indicators and topology relationships normal")

        return {
            "prefix": prefix,
            "classification_id": predicted_class_id,
            "classification_name": CLASS_NAMES.get(predicted_class_id, "Unknown"),
            "confidence": confidence,
            "trust_score": round(trust_score, 2),
            "reasons": reasons,
            "feature_vector": feature_vector.tolist(),
            "raw_probabilities": raw_probabilities.tolist()
        }
