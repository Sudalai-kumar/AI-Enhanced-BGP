"""
Hybrid Decision & Explainability Engine.
Combines statistical ML classification probabilities with deterministic safety heuristics
to compute a finalized Trust Score and diagnostic root-cause explanation.
"""

from typing import Dict, Any, Tuple
import numpy as np
from src.dataset.generator import CLASS_NAMES

class HybridDecisionEngine:
    def __init__(self, classifier=None):
        self.classifier = classifier

    def evaluate(self, prefix: str, current_route: Dict[str, Any],
                 feature_vector: np.ndarray,
                 raw_probabilities: np.ndarray) -> Dict[str, Any]:
        """
        Combines ML probabilities with deterministic rule evaluation.
        Features mapping:
        0: as_path_len
        1: as_path_edit_distance
        2: origin_as_change
        3: prefix_mask_len
        4: announcement_rate
        5: flap_count_5min
        6: loc_pref_current
        7: route_age_seconds
        8: valley_free_violation
        9: neighbor_diversity
        """
        pred_class_id = int(np.argmax(raw_probabilities))
        ml_confidence = float(raw_probabilities[pred_class_id])
        
        origin_changed = bool(feature_vector[2] > 0.5)
        valley_free_viol = bool(feature_vector[8] > 0.5)
        high_flaps = bool(feature_vector[5] >= 3)
        sub_prefix = bool(feature_vector[3] >= 24)
        
        reasons = []
        final_class = pred_class_id
        final_confidence = ml_confidence
        
        # Rule 1: Definitive Hijack Flag (Origin AS change on registered prefix)
        if origin_changed:
            final_class = 3 # Prefix Hijack Candidate
            final_confidence = max(ml_confidence, 0.95)
            reasons.append(f"Origin AS mismatch: announced AS {current_route.get('origin_as')} differs from historical origin")

        # Rule 2: Valley-free routing violation (Route Leak)
        elif valley_free_viol:
            final_class = 2 # Route Leak Candidate
            final_confidence = max(ml_confidence, 0.90)
            reasons.append("Valley-Free rule violation: multi-transit peer forwarding detected (RFC 9234)")

        # Rule 3: High Flapping / Churn
        elif high_flaps and final_class == 0:
            final_class = 1 # Elevate to Suspicious
            final_confidence = 0.85
            reasons.append(f"High route oscillation: {int(feature_vector[5])} flaps in 5-minute sliding window")

        # Rule 4: Normal Steady State
        if final_class == 0:
            reasons.append("Route matches historical origin, AS Path topology, and stable telemetry")

        # Compute Dynamic Trust Score (0.0 to 1.0)
        # Class 0 (Normal) -> Trust 0.90 - 1.00
        # Class 1 (Suspicious) -> Trust 0.50 - 0.70
        # Class 2 (Route Leak) -> Trust 0.20 - 0.40
        # Class 3 (Hijack) -> Trust 0.00 - 0.15
        if final_class == 0:
            trust_score = round(float(0.90 + (0.10 * final_confidence)), 3)
        elif final_class == 1:
            trust_score = round(float(0.70 - (0.20 * final_confidence)), 3)
        elif final_class == 2:
            trust_score = round(float(0.40 - (0.20 * final_confidence)), 3)
        else: # Hijack
            trust_score = round(float(0.15 - (0.15 * final_confidence)), 3)

        return {
            "prefix": prefix,
            "classification_id": final_class,
            "classification_name": CLASS_NAMES.get(final_class, "Unknown"),
            "confidence": round(final_confidence, 4),
            "trust_score": trust_score,
            "reasons": reasons,
            "feature_summary": {
                "as_path_len": int(feature_vector[0]),
                "origin_as_changed": origin_changed,
                "flap_count": int(feature_vector[5]),
                "valley_free_violation": valley_free_viol
            }
        }
