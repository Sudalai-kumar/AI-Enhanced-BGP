"""
Autonomous BGP Closed-Loop Controller Daemon.
Integrates:
1. Resilient Telemetry Collector & Sliding Window Buffer
2. Feature Extractor & Trained ML Classifier
3. Hybrid Decision & Trust Scoring Engine
4. Shadow Validation & Anti-Thrashing Engine
5. Automatic Rollback Manager
6. Dynamic LocalPref & Dual-Quarantine Route Map Enforcement
"""

import time
import argparse
import sys
import os
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.utils.logger import setup_logger
from src.telemetry.frr_collector import FRRTelemetryCollector
from src.ai.feature_extractor import BGPFeatureExtractor
from src.ai.classifier import BGPClassifier
from src.ai.hybrid_engine import HybridDecisionEngine
from src.policy.policy_engine import BGPPolicyEngine
from src.policy.shadow_validator import ShadowValidator
from src.policy.rollback_manager import RollbackManager

logger = setup_logger("autonomous_controller")

class AutonomousBGPController:
    def __init__(self, router: str = "as65003", peer_ip: str = "10.0.23.2",
                 poll_interval: float = 2.0, shadow_sec: float = 5.0, model_type: str = "random_forest"):
        self.router = router
        self.interval = poll_interval
        
        # Telemetry & AI Pipeline
        self.collector = FRRTelemetryCollector(router_container=router, poll_interval=poll_interval)
        self.feature_extractor = BGPFeatureExtractor()
        self.classifier = BGPClassifier(model_type=model_type)
        self.decision_engine = HybridDecisionEngine(classifier=self.classifier)
        
        # Policy & Safeguards Pipeline
        self.policy_engine = BGPPolicyEngine(router=router, peer_ip=peer_ip)
        self.shadow_validator = ShadowValidator(shadow_duration_sec=shadow_sec, required_consecutive_ticks=2)
        self.rollback_manager = RollbackManager(required_normal_ticks=3)
        
        # Active state: prefix -> current applied policy
        self.active_policies: Dict[str, Dict[str, Any]] = {}
        self.running = False

    def step(self):
        """Executes a single closed-loop observation, evaluation, and policy enforcement iteration."""
        # 1. Telemetry Ingestion
        peer_summary = self.collector.collect_bgp_summary()
        route_rib = self.collector.collect_route_rib()
        routes = route_rib.get("routes", [])
        
        if not routes:
            logger.info(f"[{self.router}] No active routes in RIB.")
            return

        policy_changed = False
        
        for r in routes:
            prefix = r["prefix"]
            history = self.collector.buffer.get_history(prefix)
            
            # 2. Real-time Feature Extraction
            features = self.feature_extractor.extract_features(
                prefix=prefix,
                current_route=r,
                sliding_window_events=history,
                active_neighbors_announcing=1
            )
            
            # 3. Model Inference & Trust Scoring
            pred_class, probs = self.classifier.predict(features)
            decision = self.decision_engine.evaluate(
                prefix=prefix,
                current_route=r,
                feature_vector=features,
                raw_probabilities=probs
            )
            
            trust = decision["trust_score"]
            c_name = decision["classification_name"]
            c_id = decision["classification_id"]
            reasons = "; ".join(decision["reasons"])
            
            current_applied_lp = self.active_policies.get(prefix, {}).get("loc_pref", 100)
            
            # 4. Map Trust to Target Policy Action
            target_lp, target_comm, action_desc = self.policy_engine.map_trust_to_policy(
                trust_score=trust,
                class_id=c_id,
                current_loc_pref=current_applied_lp
            )
            
            logger.info(
                f"[{self.router}] Prefix: {prefix:16} | Status: {c_name:22} | "
                f"Trust: {trust:.2f} | Current LP: {current_applied_lp:3} -> Target LP: {target_lp:3} | Action: {action_desc}"
            )
            
            # 5. Handle Rollback vs Escalation
            if c_id == 0:
                # Normal State -> Evaluate potential Rollback
                should_rollback, rb_status = self.rollback_manager.process_observation(prefix, is_normal=True)
                if should_rollback and current_applied_lp != 100:
                    logger.info(f"[{prefix}] Executing Autonomous Rollback to LocalPref 100.")
                    self.active_policies[prefix] = {"loc_pref": 100, "community": None}
                    policy_changed = True
            else:
                # Anomaly State -> Invalidate rollback streak & Submit to Shadow Validation
                self.rollback_manager.process_observation(prefix, is_normal=False)
                
                # Check if target policy is different from current active policy
                if target_lp != current_applied_lp or target_comm != self.active_policies.get(prefix, {}).get("community"):
                    should_promote, shadow_status = self.shadow_validator.submit_observation(
                        prefix=prefix,
                        target_loc_pref=target_lp,
                        target_community=target_comm,
                        class_id=c_id,
                        current_live_loc_pref=current_applied_lp
                    )
                    
                    if should_promote:
                        logger.warning(f"[{prefix}] Promoting Shadow Policy to LIVE enforcement: LP={target_lp}, Comm={target_comm}")
                        self.active_policies[prefix] = {"loc_pref": target_lp, "community": target_comm}
                        self.rollback_manager.register_policy_modification(prefix, target_lp, target_comm)
                        policy_changed = True
                    else:
                        logger.info(f"[{prefix}] Staged: {shadow_status}")

        # 6. Apply Live Policy Updates if any changes occurred
        if policy_changed:
            logger.info(f"[{self.router}] Applying updated route-maps to live FRR control plane...")
            self.policy_engine.apply_policy(self.active_policies, settle_delay_sec=0.5)

    def run(self, duration: Optional[float] = None):
        """Runs the continuous autonomous closed-loop control daemon."""
        logger.info(f"Starting Autonomous BGP Closed-Loop Controller on [{self.router}]...")
        self.running = True
        start_time = time.time()
        
        try:
            while self.running:
                self.step()
                if duration and (time.time() - start_time) >= duration:
                    logger.info(f"Completed requested duration {duration}s.")
                    break
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Autonomous Controller stopped by operator.")
        finally:
            self.running = False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous BGP Controller")
    parser.add_argument("--router", default="as65003", help="Target router container")
    parser.add_argument("--peer", default="10.0.23.2", help="Inbound peering IP")
    parser.add_argument("--interval", type=float, default=2.0, help="Control loop interval (sec)")
    parser.add_argument("--duration", type=float, default=None, help="Optional run duration (sec)")
    parser.add_argument("--shadow", type=float, default=4.0, help="Shadow validation duration (sec)")
    parser.add_argument("--model", choices=["random_forest", "logistic_regression"], default="random_forest", help="Classifier model")
    args = parser.parse_args()

    controller = AutonomousBGPController(
        router=args.router,
        peer_ip=args.peer,
        poll_interval=args.interval,
        shadow_sec=args.shadow,
        model_type=args.model
    )
    controller.run(duration=args.duration)
