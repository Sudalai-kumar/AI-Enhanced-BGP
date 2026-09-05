"""
Production Closed-Loop Autonomous BGP Controller (Asynchronous Event-Driven Pipeline).

Architecture:
  Runs 5 concurrent cooperative coroutines orchestrated via asyncio:
  1. _telemetry_loop:   Polls FRR periodically, constructs full snapshots with history, feeds snapshot queue.
  2. _inference_loop:   Consumes snapshots, extracts 10-feature vectors, runs ML + hybrid trust, feeds decision queue.
  3. _policy_actor:     Single consumer that batches decisions per snapshot, enforces anti-thrashing safeguards,
                        and performs atomic all-or-nothing policy application to FRR and persistent state.
  4. _heartbeat_loop:   Monitors peer reachability using cached peer states without redundant Docker calls.
  5. _metrics_loop:     Collects system metrics (CPU/RAM) independently.

Features:
- Async Startup State Reconciliation against Live FRR State.
- Non-corrupting Thread-Safe State Store Persistence.
- Strict Atomic Policy Application with Rollback on Failure.
- Live FRR Reachability Checking for Multi-Criteria Recovery.
- Independent Detection and Mitigation Event Recording for Live MTTD/MTTM Measurement.
"""

import time
import argparse
import sys
import os
import asyncio
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.utils.logger import setup_logger
from src.utils.async_utils import configure_asyncio_policy
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
    def __init__(self, router: str = "as65003", peer_ip: str = "10.0.13.2",
                 poll_interval: float = 1.0, shadow_sec: float = 4.0, model_type: str = "random_forest",
                 total_configured_peers: int = 3, heartbeat_interval: float = 10.0,
                 metrics_interval: float = 5.0,
                 baseline_origin_as: int = 65007,
                 baseline_as_path: str = "65003 65001"):
        self.router = router
        self.peer_ip = peer_ip
        self.interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self.metrics_interval = metrics_interval

        # Telemetry & AI Pipeline
        self.collector = FRRTelemetryCollector(router_container=router, poll_interval=poll_interval, total_configured_peers=total_configured_peers)
        self.feature_extractor = BGPFeatureExtractor(baseline_origin_as=baseline_origin_as, baseline_as_path=baseline_as_path)
        self.classifier = BGPClassifier(model_type=model_type)
        self.decision_engine = HybridDecisionEngine(classifier=self.classifier)

        # Policy, Safeguards & State Store
        self.policy_engine = BGPPolicyEngine(router=router, peer_ip=peer_ip)
        self.shadow_validator = ShadowValidator(shadow_duration_sec=shadow_sec, required_consecutive_ticks=2)
        self.rollback_manager = RollbackManager(required_normal_ticks=3)
        self.state_store = ControllerStateStore(router_name=router)

        # Controller-owned inter-task queues and synchronization
        self._snapshot_q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._decision_q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._shutdown: asyncio.Event = asyncio.Event()

        self.active_policies: Dict[str, Dict[str, Any]] = {}
        self._snapshot_counter: int = 0
        self.running = False

    async def _initialize(self):
        """Async initialization for state stores and startup reconciliation."""
        await self.state_store.initialize()
        await self.collector.storage.initialize()
        await self._reconcile_startup_state()

    async def _reconcile_startup_state(self):
        """Reconciles persisted SQLite policies against verified live FRR state on startup."""
        stored_policies = await self.state_store.get_all_active_policies()
        frr_verified = await self.policy_engine.verify_frr_state(stored_policies) if stored_policies else True

        if frr_verified:
            self.active_policies = stored_policies
            logger.info(f"[{self.router}] Reconciled and verified {len(self.active_policies)} active policies against live FRR.")
        else:
            logger.warning(f"[{self.router}] Discrepancy between SQLite and FRR! Re-synchronizing FRR state...")
            success = await self.policy_engine.apply_policy(stored_policies)
            if success:
                self.active_policies = stored_policies
                logger.info(f"[{self.router}] FRR state successfully re-synchronized with persistent store.")
            else:
                logger.error(f"[{self.router}] Failed to re-synchronize FRR. Clearing stale persistent overrides.")
                for pfx in list(stored_policies.keys()):
                    await self.state_store.remove_policy(pfx)
                self.active_policies = {}

    async def _telemetry_loop(self):
        """Stage 1: Polls FRR periodically, constructs full snapshots, feeds snapshot queue."""
        logger.info(f"[{self.router}] Telemetry loop started (interval: {self.interval}s).")
        while not self._shutdown.is_set():
            try:
                self._snapshot_counter += 1
                snap_id = self._snapshot_counter
                await self.collector.collect_bgp_summary()
                snapshot = await self.collector.collect_snapshot(snap_id)
                if snapshot.get("routes_with_history"):
                    await self._snapshot_q.put(snapshot)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.router}] Error in telemetry loop: {e}", exc_info=True)

            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break

    async def _inference_loop(self):
        """Stage 2: Consumes snapshots, runs feature extraction and ML inference, feeds decision queue."""
        logger.info(f"[{self.router}] Inference loop started.")
        while not self._shutdown.is_set():
            try:
                try:
                    snapshot = await asyncio.wait_for(self._snapshot_q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                decisions = []
                for item in snapshot.get("routes_with_history", []):
                    route = item["route"]
                    history = item["history"]
                    prefix = route["prefix"]

                    # Feature Extraction
                    features = self.feature_extractor.extract_features(
                        prefix=prefix,
                        current_route=route,
                        sliding_window_events=history,
                        active_neighbors_announcing=route.get("active_neighbors", 1),
                        total_known_peers=self.collector.total_configured_peers
                    )

                    # Model Inference & Trust Scoring
                    pred_class, probs = self.classifier.predict(features)
                    decision = self.decision_engine.evaluate(
                        prefix=prefix,
                        current_route=route,
                        feature_vector=features,
                        raw_probabilities=probs
                    )

                    current_applied_lp = self.active_policies.get(prefix, {}).get("loc_pref", 100)
                    target_lp, target_comm, action_desc = self.policy_engine.map_trust_to_policy(
                        trust_score=decision["trust_score"],
                        class_id=decision["classification_id"],
                        current_loc_pref=current_applied_lp
                    )

                    decisions.append({
                        "prefix": prefix,
                        "route": route,
                        "features": features,
                        "decision": decision,
                        "target_lp": target_lp,
                        "target_comm": target_comm,
                        "action_desc": action_desc
                    })

                batch = {
                    "snapshot_id": snapshot["snapshot_id"],
                    "collected_at": snapshot["collected_at"],
                    "decisions": decisions
                }
                await self._decision_q.put(batch)
                self._snapshot_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.router}] Error in inference loop: {e}", exc_info=True)

    async def _policy_actor(self):
        """
        Stage 3: Dedicated policy actor.
        Single entity that mutates active_policies, applies vtysh config, and writes to state store.
        Rejects stale snapshot batches and enforces atomic state transitions.
        """
        logger.info(f"[{self.router}] Policy actor started.")
        last_processed_snapshot = 0

        while not self._shutdown.is_set():
            try:
                try:
                    batch = await asyncio.wait_for(self._decision_q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if batch["snapshot_id"] <= last_processed_snapshot:
                    logger.warning(
                        f"[{self.router}] Discarding stale batch (snapshot {batch['snapshot_id']} "
                        f"<= last processed {last_processed_snapshot})"
                    )
                    self._decision_q.task_done()
                    continue

                policy_updates_pending = False
                new_active_state = self.active_policies.copy()
                pending_meta: Dict[str, Dict[str, Any]] = {}

                for d in batch["decisions"]:
                    prefix = d["prefix"]
                    features = d["features"]
                    decision = d["decision"]
                    target_lp = d["target_lp"]
                    target_comm = d["target_comm"]
                    action_desc = d["action_desc"]
                    c_id = decision["classification_id"]
                    trust = decision["trust_score"]
                    c_name = decision["classification_name"]

                    current_applied_lp = self.active_policies.get(prefix, {}).get("loc_pref", 100)

                    logger.info(
                        f"[{self.router}] Prefix: {prefix:16} | Status: {c_name:22} | "
                        f"Trust: {trust:.2f} | Current LP: {current_applied_lp:3} -> Target LP: {target_lp:3} | Action: {action_desc}"
                    )

                    if c_id == 0:
                        origin_stable = (features[2] == 0.0)
                        path_stable = (features[8] == 0.0)
                        flaps_quiescent = (features[5] == 0.0)
                        is_reachable = self.collector.check_cached_reachability(self.peer_ip)

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
                        current_comm = self.active_policies.get(prefix, {}).get("community")
                        if target_lp != current_applied_lp or target_comm != current_comm:
                            should_promote, shadow_status = self.shadow_validator.submit_observation(
                                prefix=prefix,
                                target_loc_pref=target_lp,
                                target_community=target_comm,
                                class_id=c_id,
                                current_live_loc_pref=current_applied_lp
                            )

                            if should_promote:
                                logger.warning(f"[{prefix}] Promoting Shadow Policy to LIVE: LP={target_lp}, Comm={target_comm}")
                                await self.state_store.record_detection(
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

                # Atomic policy commit
                if policy_updates_pending:
                    verified = await self.policy_engine.apply_policy(new_active_state, settle_delay_sec=0.4)
                    if verified:
                        self.active_policies = new_active_state.copy()
                        for pfx, pol in self.active_policies.items():
                            c_id = pol.get("classification_id", 3)
                            t_score = pol.get("trust_score", 0.0)
                            await self.state_store.save_policy(pfx, pol["loc_pref"], pol.get("community"), c_id, t_score, verified=True)

                        for pfx in pending_meta:
                            mitigated = await self.state_store.record_mitigation(pfx)
                            if mitigated:
                                logger.info(f"[{pfx}] Mitigation timestamp recorded in detection_events.")

                        for pfx in list((await self.state_store.get_all_active_policies()).keys()):
                            if pfx not in self.active_policies:
                                await self.state_store.remove_policy(pfx)
                        logger.info(f"[{self.router}] State store committed with verified active policies.")
                    else:
                        logger.error(f"[{self.router}] FRR state verification failed! Rolling back memory to previous state.")

                last_processed_snapshot = batch["snapshot_id"]
                self._decision_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.router}] Error in policy actor: {e}", exc_info=True)

    async def _heartbeat_loop(self):
        """Stage 4: Monitors peer reachability using cached summary without extra Docker calls."""
        logger.info(f"[{self.router}] Heartbeat loop started (interval: {self.heartbeat_interval}s).")
        while not self._shutdown.is_set():
            try:
                reachable = self.collector.check_cached_reachability(self.peer_ip)
                logger.debug(f"[{self.router}] Heartbeat: peer {self.peer_ip} reachable={reachable}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[{self.router}] Heartbeat check warning: {e}")

            try:
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break

    async def _metrics_loop(self):
        """Stage 5: Independent CPU/RAM utilization metrics collector."""
        logger.info(f"[{self.router}] Metrics loop started (interval: {self.metrics_interval}s).")
        while not self._shutdown.is_set():
            try:
                await self.collector.collect_system_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[{self.router}] Metrics collection warning: {e}")

            try:
                await asyncio.sleep(self.metrics_interval)
            except asyncio.CancelledError:
                break

    async def run(self, duration: Optional[float] = None):
        """Runs the continuous asynchronous event-driven control plane pipeline."""
        await self._initialize()
        logger.info(f"Starting Async Autonomous BGP Controller on [{self.router}]...")
        self.running = True
        tasks = [
            asyncio.create_task(self._telemetry_loop(), name="telemetry"),
            asyncio.create_task(self._inference_loop(), name="inference"),
            asyncio.create_task(self._policy_actor(), name="policy_actor"),
            asyncio.create_task(self._heartbeat_loop(), name="heartbeat"),
            asyncio.create_task(self._metrics_loop(), name="metrics"),
        ]

        try:
            if duration:
                await asyncio.sleep(duration)
                self._shutdown.set()
            else:
                while self.running and not self._shutdown.is_set():
                    await asyncio.sleep(1.0)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Autonomous Controller stopping on signal...")
            self._shutdown.set()
        finally:
            self.running = False
            self._shutdown.set()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"[{self.router}] Async Autonomous Controller shut down cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Async Autonomous BGP Controller")
    parser.add_argument("--router", default="as65003", help="Target router container")
    parser.add_argument("--peer", default="10.0.13.2", help="Inbound peering IP")
    parser.add_argument("--peers", type=int, default=3, help="Total configured peers count")
    parser.add_argument("--interval", type=float, default=1.0, help="Control loop interval (sec)")
    parser.add_argument("--duration", type=float, default=None, help="Optional run duration (sec)")
    parser.add_argument("--shadow", type=float, default=4.0, help="Shadow validation duration (sec)")
    parser.add_argument("--model", choices=["random_forest", "logistic_regression"], default="random_forest", help="Classifier model")
    parser.add_argument("--heartbeat", type=float, default=10.0, help="Heartbeat interval (sec)")
    parser.add_argument("--metrics-interval", type=float, default=5.0, help="Metrics interval (sec)")
    parser.add_argument("--baseline-origin", type=int, default=65007, help="Baseline origin AS")
    parser.add_argument("--baseline-path", default="65003 65001", help="Baseline AS path")
    args = parser.parse_args()

    configure_asyncio_policy()

    controller = AutonomousBGPController(
        router=args.router,
        peer_ip=args.peer,
        poll_interval=args.interval,
        shadow_sec=args.shadow,
        model_type=args.model,
        total_configured_peers=args.peers,
        heartbeat_interval=args.heartbeat,
        metrics_interval=args.metrics_interval,
        baseline_origin_as=args.baseline_origin,
        baseline_as_path=args.baseline_path
    )
    asyncio.run(controller.run(duration=args.duration))
