"""
Production Closed-Loop Autonomous BGP Controller (Synchronous Polling Architecture).

Architecture note:
  This controller uses a synchronous polling loop — not an event-driven async framework.
  Each iteration (step) collects telemetry, classifies prefixes, makes policy decisions,
  and applies FRR configuration changes sequentially before sleeping for poll_interval.
  This is intentional for lab reproducibility and deterministic state management.

Features:
- Startup State Reconciliation against Live FRR State.
- Non-corrupting State Store Persistence.
- Strict Atomic Policy Application with Rollback on Failure.
- Live FRR Reachability Checking for Multi-Criteria Recovery.
- Detection and Mitigation Event Recording for Live MTTD/MTTM Measurement.
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
from src.policy.state_store import ControllerStateStore

logger = setup_logger("autonomous_controller")

class AutonomousBGPController:
    def __init__(self, router: str = "as65003", peer_ip: str = "10.0.23.2",
                 poll_interval: float = 1.0, shadow_sec: float = 4.0, model_type: str = "random_forest",
                 total_configured_peers: int = 2):
        self.router = router
        self.peer_ip = peer_ip
        self.interval = poll_interval

        # Telemetry & AI Pipeline
        self.collector = FRRTelemetryCollector(router_container=router, poll_interval=poll_interval, total_configured_peers=total_configured_peers)
        self.feature_extractor = BGPFeatureExtractor()
        self.classifier = BGPClassifier(model_type=model_type)
        self.decision_engine = HybridDecisionEngine(classifier=self.classifier)

        # Policy, Safeguards & State Store
        self.policy_engine = BGPPolicyEngine(router=router, peer_ip=peer_ip)
        self.shadow_validator = ShadowValidator(shadow_duration_sec=shadow_sec, required_consecutive_ticks=2)
        self.rollback_manager = RollbackManager(required_normal_ticks=3)
        self.state_store = ControllerStateStore()

        # True Reconciliation between SQLite and Live FRR
        self.active_policies: Dict[str, Dict[str, Any]] = {}
        self._reconcile_startup_state()
        self.running = False

    def _reconcile_startup_state(self):
        """Reconciles persisted SQLite policies against verified live FRR state on startup."""
        stored_policies = self.state_store.get_all_active_policies()
        frr_verified = self.policy_engine.verify_frr_state(stored_policies) if stored_policies else True

        if frr_verified:
            self.active_policies = stored_policies
            logger.info(f"[{self.router}] Reconciled and verified {len(self.active_policies)} active policies against live FRR.")
        else:
            logger.warning(f"[{self.router}] Discrepancy between SQLite and FRR! Re-synchronizing FRR state...")
            success = self.policy_engine.apply_policy(stored_policies)
            if success:
                self.active_policies = stored_policies
                logger.info(f"[{self.router}] FRR state successfully re-synchronized with persistent store.")
            else:
                logger.error(f"[{self.router}] Failed to re-synchronize FRR. Clearing stale persistent overrides.")
                for pfx in list(stored_policies.keys()):
                    self.state_store.remove_policy(pfx)
                self.active_policies = {}

    def step(self):
        """Executes a single synchronous observation, classification, trust scoring,
        and policy enforcement cycle."""
        # 1. Telemetry Ingestion with System Metrics & RIB Transition Tracking
        self.collector.collect_bgp_summary()
        self.collector.collect_system_metrics()
        route_rib = self.collector.collect_route_rib()
        routes = route_rib.get("routes", [])

        if not routes:
            return

        policy_updates_pending = False
        new_active_state = self.active_policies.copy()

        # Track pending policy metadata so we don't corrupt classification_id or trust
        pending_meta: Dict[str, Dict[str, Any]] = {}

        for r in routes:
            prefix = r["prefix"]
            history = self.collector.buffer.get_history(prefix)

            # 2. Extract Features with Configured Peer Denominator
            features = self.feature_extractor.extract_features(
                prefix=prefix,
                current_route=r,
                sliding_window_events=history,
                active_neighbors_announcing=r.get("active_neighbors", 1),
                total_known_peers=self.collector.total_configured_peers
            )

            # 3. Model Inference & Multi-Factor Trust Scoring
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

            current_applied_lp = self.active_policies.get(prefix, {}).get("loc_pref", 100)

            # 4. Map Trust to Policy Action
            target_lp, target_comm, action_desc = self.policy_engine.map_trust_to_policy(
                trust_score=trust,
                class_id=c_id,
                current_loc_pref=current_applied_lp
            )

            logger.info(
                f"[{self.router}] Prefix: {prefix:16} | Status: {c_name:22} | "
                f"Trust: {trust:.2f} | Current LP: {current_applied_lp:3} -> Target LP: {target_lp:3} | Action: {action_desc}"
            )

            # 5. Multi-Criteria Rollback vs Escalation
            if c_id == 0:
                origin_stable = (features[2] == 0.0)
                path_stable = (features[8] == 0.0)
                flaps_quiescent = (features[5] == 0.0)
                # Verify real FRR reachability of the next hop
                is_reachable = self.collector.verify_nexthop_reachability(self.peer_ip)

                should_rollback, rb_status = self.rollback_manager.process_observation(
                    prefix=prefix,
                    is_normal=True,
                    origin_stable=origin_stable,
                    path_stable=path_stable,
                    flaps_quiescent=flaps_quiescent,
                    frr_reachable=is_reachable
                )

                if should_rollback and current_applied_lp != 100:
                    logger.info(f"[{prefix}] Multi-Criteria Health Confirmed: Triggering Rollback to LP 100.")
                    new_active_state.pop(prefix, None)
                    policy_updates_pending = True
            else:
                self.rollback_manager.process_observation(prefix, is_normal=False)

                if target_lp != current_applied_lp or target_comm != self.active_policies.get(prefix, {}).get("community"):
                    should_promote, shadow_status = self.shadow_validator.submit_observation(
                        prefix=prefix,
                        target_loc_pref=target_lp,
                        target_community=target_comm,
                        class_id=c_id,
                        current_live_loc_pref=current_applied_lp
                    )

                    if should_promote:
                        logger.warning(f"[{prefix}] Promoting Shadow Policy to LIVE: LP={target_lp}, Comm={target_comm}")

                        # Record detection timestamp BEFORE apply_policy.
                        # This timestamp is used to compute MTTD independently of MTTM.
                        self.state_store.record_detection(
                            prefix=prefix,
                            class_id=c_id,
                            trust_score=trust
                        )

                        new_active_state[prefix] = {
                            "loc_pref": target_lp,
                            "community": target_comm,
                            "classification_id": c_id,
                            "trust_score": trust
                        }
                        pending_meta[prefix] = {
                            "classification_id": c_id,
                            "trust_score": trust
                        }
                        self.rollback_manager.register_policy_modification(prefix, target_lp, target_comm)
                        policy_updates_pending = True
                    else:
                        logger.info(f"[{prefix}] Staged in shadow queue: {shadow_status}")

        # 6. Atomic Policy Application & Atomic State Persistence
        if policy_updates_pending:
            verified = self.policy_engine.apply_policy(new_active_state, settle_delay_sec=0.4)
            if verified:
                self.active_policies = new_active_state.copy()
                # Persist accurate metadata only after successful FRR verification
                for pfx, pol in self.active_policies.items():
                    c_id = pol.get("classification_id", 3)
                    t_score = pol.get("trust_score", 0.0)
                    self.state_store.save_policy(pfx, pol["loc_pref"], pol.get("community"), c_id, t_score, verified=True)

                # Record mitigation timestamp AFTER successful FRR application.
                # MTTM = mitigated_at - t_attack_injected (measured independently of MTTD).
                for pfx in pending_meta:
                    mitigated = self.state_store.record_mitigation(pfx)
                    if mitigated:
                        logger.info(f"[{pfx}] Mitigation timestamp recorded in detection_events.")

                # Remove restored prefixes from persistent store
                for pfx in list(self.state_store.get_all_active_policies().keys()):
                    if pfx not in self.active_policies:
                        self.state_store.remove_policy(pfx)
                logger.info(f"[{self.router}] State store committed with verified active policies.")
            else:
                logger.error(f"[{self.router}] FRR state verification failed! Rolling back memory to previous state.")

    def run(self, duration: Optional[float] = None):
        """Runs the continuous synchronous polling control loop."""
        logger.info(f"Starting Autonomous BGP Controller on [{self.router}]...")
        self.running = True
        start_time = time.time()

        try:
            # Synchronous polling loop: step() -> sleep(interval) -> repeat.
            # Not event-driven; every iteration is sequential and blocking.
            while self.running:
                self.step()
                if duration and (time.time() - start_time) >= duration:
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
    parser.add_argument("--interval", type=float, default=1.0, help="Control loop interval (sec)")
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
