"""
Ablation Experiment Variant Configuration for AI-Enhanced BGP Control Plane.

Defines the 5 formal architectural variants:
- A0: Standard BGP only (RFC standard baseline, no anomaly detector, no mitigation)
- A1: BGP + Heuristic / rule-based detection (deterministic rules, static policy mapping, immediate action)
- A2: BGP + ML classifier only (Random Forest inference, direct class-to-policy mapping without trust weighting)
- A3: BGP + ML + Behavioral Trust (ML inference + multi-factor continuous trust score, immediate action)
- A4: Full proposed system (ML + behavioral trust + shadow staging + atomic commit + rollback)
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any


class AblationVariant(str, Enum):
    A0 = "A0"  # Standard BGP
    A1 = "A1"  # Heuristic / Rule-based
    A2 = "A2"  # ML Classifier Only
    A3 = "A3"  # ML + Behavioral Trust
    A4 = "A4"  # Full Proposed Architecture


@dataclass
class VariantConfig:
    variant_id: str
    name: str
    description: str
    use_detector: bool
    detector_type: str  # "none", "heuristic", "ml"
    use_trust_score: bool
    use_shadow_validation: bool
    use_autonomous_mitigation: bool
    use_automatic_rollback: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "name": self.name,
            "description": self.description,
            "use_detector": self.use_detector,
            "detector_type": self.detector_type,
            "use_trust_score": self.use_trust_score,
            "use_shadow_validation": self.use_shadow_validation,
            "use_autonomous_mitigation": self.use_autonomous_mitigation,
            "use_automatic_rollback": self.use_automatic_rollback,
        }


VARIANT_REGISTRY: Dict[str, VariantConfig] = {
    "A0": VariantConfig(
        variant_id="A0",
        name="Standard BGP",
        description="Standard RFC 4271 BGP protocol execution without anomaly detection or policy intervention.",
        use_detector=False,
        detector_type="none",
        use_trust_score=False,
        use_shadow_validation=False,
        use_autonomous_mitigation=False,
        use_automatic_rollback=False,
    ),
    "A1": VariantConfig(
        variant_id="A1",
        name="BGP + Heuristics",
        description="Deterministic rule-based anomaly detection with immediate static route-map application.",
        use_detector=True,
        detector_type="heuristic",
        use_trust_score=False,
        use_shadow_validation=False,
        use_autonomous_mitigation=True,
        use_automatic_rollback=True,
    ),
    "A2": VariantConfig(
        variant_id="A2",
        name="BGP + ML Only",
        description="Trained Random Forest classifier mapping predicted class directly to policy without behavioral trust scoring.",
        use_detector=True,
        detector_type="ml",
        use_trust_score=False,
        use_shadow_validation=False,
        use_autonomous_mitigation=True,
        use_automatic_rollback=True,
    ),
    "A3": VariantConfig(
        variant_id="A3",
        name="BGP + ML + Behavioral Trust",
        description="Random Forest classifier combined with 6-factor continuous behavioral trust scoring, applied immediately.",
        use_detector=True,
        detector_type="ml",
        use_trust_score=True,
        use_shadow_validation=False,
        use_autonomous_mitigation=True,
        use_automatic_rollback=True,
    ),
    "A4": VariantConfig(
        variant_id="A4",
        name="Full Proposed System",
        description="Full closed-loop architecture: ML classifier + Behavioral Trust + Shadow Staging + Atomic Commit + Multi-Criteria Rollback.",
        use_detector=True,
        detector_type="ml",
        use_trust_score=True,
        use_shadow_validation=True,
        use_autonomous_mitigation=True,
        use_automatic_rollback=True,
    ),
}


def get_variant_config(variant_name: str) -> VariantConfig:
    norm = variant_name.upper().strip()
    if norm in VARIANT_REGISTRY:
        return VARIANT_REGISTRY[norm]
    raise ValueError(f"Unknown ablation variant '{variant_name}'. Expected one of {list(VARIANT_REGISTRY.keys())}")
