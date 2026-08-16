"""
CLI Entrypoint to launch the Asynchronous BGP AI Agent.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.ai.agent import BGPAIAgent

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch BGP AI Control Plane Agent")
    parser.add_argument("--router", default="as65003", help="Target FRRouting container")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval (seconds)")
    parser.add_argument("--duration", type=float, default=None, help="Optional duration limit (seconds)")
    parser.add_argument("--model", choices=["random_forest", "logistic_regression"], default="random_forest", help="Model type")
    args = parser.parse_args()

    agent = BGPAIAgent(router=args.router, poll_interval=args.interval, model_type=args.model)
    agent.run(duration=args.duration)
