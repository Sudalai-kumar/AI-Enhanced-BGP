"""
Asynchronous AI Control Plane Agent.
Executes an event loop adjacent to FRRouting on AS65003:
1. Ingests live telemetry from FRR (via sliding-window buffer).
2. Extracts 10 normalized features per prefix.
3. Performs ML classification & hybrid trust scoring.
4. Logs real-time decisions to SQLite and issues diagnostic alerts.
"""

import time
import argparse
import sys
import os
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.utils.logger import setup_logger
from src.telemetry.frr_collector import FRRTelemetryCollector
from src.ai.feature_extractor import BGPFeatureExtractor
from src.ai.classifier import BGPClassifier
from src.ai.hybrid_engine import HybridDecisionEngine

logger = setup_logger("bgp_ai_agent")

class BGPAIAgent:
    def __init__(self, router: str = "as65003", poll_interval: float = 2.0, model_type: str = "random_forest"):
        self.router = router
        self.interval = poll_interval
        self.collector = FRRTelemetryCollector(router_container=router, poll_interval=poll_interval)
        self.feature_extractor = BGPFeatureExtractor()
        self.classifier = BGPClassifier(model_type=model_type)
        self.decision_engine = HybridDecisionEngine(classifier=self.classifier)
        self.running = False

    def process_iteration(self):
        """Samples telemetry, extracts features for all active prefixes, and evaluates trust."""
        # 1. Collect live RIB and Peer state
        peer_summary = self.collector.collect_bgp_summary()
        route_rib = self.collector.collect_route_rib()
        
        routes = route_rib.get("routes", [])
        if not routes:
            logger.info(f"[{self.router}] No active routes in RIB.")
            return

        for r in routes:
            prefix = r["prefix"]
            history = self.collector.buffer.get_history(prefix)
            
            # 2. Extract 10-feature vector
            features = self.feature_extractor.extract_features(
                prefix=prefix,
                current_route=r,
                sliding_window_events=history,
                active_neighbors_announcing=1
            )
            
            # 3. Model Inference
            start_infer = time.time()
            pred_class, probs = self.classifier.predict(features)
            infer_duration_ms = (time.time() - start_infer) * 1000.0
            
            # 4. Hybrid Decision & Trust Scoring
            decision = self.decision_engine.evaluate(
                prefix=prefix,
                current_route=r,
                feature_vector=features,
                raw_probabilities=probs
            )
            
            # 5. Structured Alert Logging
            c_name = decision["classification_name"]
            trust = decision["trust_score"]
            conf = decision["confidence"]
            reasons = "; ".join(decision["reasons"])
            
            log_msg = (
                f"[{self.router}] Prefix: {prefix:16} | Status: {c_name:22} | "
                f"Trust: {trust:.2f} | Conf: {conf*100:.1f}% | Inference: {infer_duration_ms:.2f}ms | Reason: {reasons}"
            )
            
            if decision["classification_id"] == 0:
                logger.info(log_msg)
            elif decision["classification_id"] == 1:
                logger.warning(log_msg)
            else:
                logger.error(log_msg)

    def run(self, duration: Optional[float] = None):
        """Runs the continuous asynchronous agent event loop."""
        logger.info(f"Starting AI Control Plane Agent on [{self.router}] (Interval: {self.interval}s)...")
        self.running = True
        start_time = time.time()
        
        try:
            while self.running:
                self.process_iteration()
                if duration and (time.time() - start_time) >= duration:
                    logger.info(f"Completed requested {duration}s execution duration.")
                    break
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("AI Agent loop stopped by operator.")
        finally:
            self.running = False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BGP AI Agent")
    parser.add_argument("--router", default="as65003", help="Target FRR router container")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds")
    parser.add_argument("--duration", type=float, default=None, help="Optional duration limit in seconds")
    parser.add_argument("--model", choices=["random_forest", "logistic_regression"], default="random_forest", help="Classifier model")
    args = parser.parse_args()

    agent = BGPAIAgent(router=args.router, poll_interval=args.interval, model_type=args.model)
    agent.run(duration=args.duration)
