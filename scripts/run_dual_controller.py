#!/usr/bin/env python3
"""
Dual Autonomous BGP Control Plane Runner (Core + Edge Decentralized Multi-Agent Defense).

Orchestrates two independent concurrent AI control plane agents in a single Python event loop:
1. Core Controller (AS65001):
   - Tier-1 Transit Backbone defense peering with AS65002.
   - First line of defense stopping cross-backbone route propagation and transit leaks.
2. Edge Controller (AS65003):
   - Regional edge defense protecting Stub Customers (AS65007, AS65008).
   - Second line of defense ensuring customer stub traffic isolation.

Both controllers operate with completely isolated queues, SQLite state databases,
and independent VTysh policy management.
"""

import sys
import os
import argparse
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.utils.logger import setup_logger
from src.utils.async_utils import configure_asyncio_policy
from scripts.run_autonomous_controller import AutonomousBGPController

logger = setup_logger("dual_controller")


async def run_dual_controllers(duration: float = None, model: str = "random_forest", interval: float = 1.0):
    logger.info("=" * 70)
    logger.info("Initializing Dual Autonomous BGP Controllers (Multi-Tier Defense)")
    logger.info("  [1] Core Defender: AS65001 (Peering with AS65002 Tier-1)")
    logger.info("  [2] Edge Defender: AS65003 (Protecting Customer Stubs AS65007/8)")
    logger.info("=" * 70)

    # Core Defender: AS65001 (Peers: AS65002, AS65003, AS65004)
    ctrl_core = AutonomousBGPController(
        router="as65001",
        peer_ip="10.0.12.3",
        poll_interval=interval,
        total_configured_peers=3,
        model_type=model,
        baseline_origin_as=65007,
        baseline_as_path="65003 65001"
    )

    # Edge Defender: AS65003 (Peers: AS65001, AS65007, AS65008)
    ctrl_edge = AutonomousBGPController(
        router="as65003",
        peer_ip="10.0.13.2",
        poll_interval=interval,
        total_configured_peers=3,
        model_type=model,
        baseline_origin_as=65007,
        baseline_as_path="65003 65001"
    )

    try:
        await asyncio.gather(
            ctrl_core.run(duration=duration),
            ctrl_edge.run(duration=duration)
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Dual Controller runner received stop signal.")
    finally:
        logger.info("Both Core and Edge controllers shut down cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dual Autonomous BGP Controller Runner")
    parser.add_argument("--duration", type=float, default=None, help="Optional duration in seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="Telemetry poll interval")
    parser.add_argument("--model", choices=["random_forest", "logistic_regression"], default="random_forest", help="AI classifier")
    args = parser.parse_args()

    configure_asyncio_policy()
    asyncio.run(run_dual_controllers(duration=args.duration, model=args.model, interval=args.interval))
