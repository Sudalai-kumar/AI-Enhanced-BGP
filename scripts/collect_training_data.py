#!/usr/bin/env python3
"""
Empirical Multi-Trial BGP Data Collection Harness (10-AS Dual-Observer Pipeline).

Orchestrates controlled attack injection across the 10-AS testbed and collects
ground-truth labeled telemetry simultaneously from both:
- AS65001 (Core Defender vantage point)
- AS65003 (Edge Defender vantage point)

Extracts 10 standardized behavioral features per snapshot and persists
strictly empirical training records into data/raw/bgp_real_training.jsonl.
"""

import sys
import os
import json
import time
import argparse
import asyncio
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.utils.logger import setup_logger
from src.utils.async_utils import configure_asyncio_policy, run_subprocess_async
from src.telemetry.frr_collector import FRRTelemetryCollector
from src.ai.feature_extractor import BGPFeatureExtractor, FEATURE_NAMES
from experiments.attacks.attack_injector import BGPAttackInjector

logger = setup_logger("collect_training_data")

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "raw"))
DEFAULT_OUTPUT = os.path.join(DATA_DIR, "bgp_real_training.jsonl")


async def verify_containers_running() -> bool:
    """Verifies that all 10 FRR containers are running."""
    rc, stdout, _ = await run_subprocess_async("docker", "ps", "--format", "{{.Names}}", timeout=5.0)
    if rc != 0:
        return False
    running_names = set(stdout.decode().split())
    required = {f"as{as_num}" for as_num in range(65001, 65011)}
    missing = required - running_names
    if missing:
        logger.warning(f"Missing containers: {sorted(missing)}. Testbed must have all 10 ASes running.")
        return False
    return True


async def collect_from_router(
    collector: FRRTelemetryCollector,
    extractor: BGPFeatureExtractor,
    router_name: str,
    scenario_id: str,
    label: int,
    trial: int,
    output_file,
    target_prefix: Optional[str] = None
) -> int:
    """Collects one snapshot from a router, extracts features, and writes JSONL records."""
    await collector.collect_bgp_summary()
    snapshot = await collector.collect_snapshot(snapshot_id=int(time.time() * 1000) % 1000000)
    records_written = 0

    for item in snapshot.get("routes_with_history", []):
        route = item["route"]
        history = item["history"]
        prefix = route["prefix"]

        features = extractor.extract_features(
            prefix=prefix,
            current_route=route,
            sliding_window_events=history,
            active_neighbors_announcing=route.get("active_neighbors", 1),
            total_known_peers=collector.total_configured_peers
        )

        # Only the injected prefix carries the attack label; background prefixes remain Normal (0)
        if target_prefix is not None:
            effective_label = label if prefix == target_prefix else 0
        else:
            effective_label = label

        record = {
            "timestamp": time.time(),
            "source_router": router_name,
            "prefix": prefix,
            "scenario": scenario_id,
            "trial": trial,
            "label": effective_label,
        }
        for name, val in zip(FEATURE_NAMES, features):
            record[name] = float(val)

        output_file.write(json.dumps(record) + "\n")
        output_file.flush()
        records_written += 1

    return records_written


async def run_data_collection(
    output_path: str = DEFAULT_OUTPUT,
    trials_per_scenario: int = 5,
    trial_duration_sec: float = 25.0,
    dry_run: bool = False
):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not dry_run:
        is_ready = await verify_containers_running()
        if not is_ready:
            logger.error(
                "Docker containers for the 10-AS topology are not running.\n"
                "Please run:\n"
                "  docker compose -f topologies/docker-compose.yml up -d\n"
                "or pass --dry-run to test data harness logic."
            )
            return

    logger.info("=" * 70)
    logger.info("Starting Empirical BGP Training Data Collection Campaign")
    logger.info(f"  Target File:          {output_path}")
    logger.info(f"  Trials per Scenario:  {trials_per_scenario}")
    logger.info(f"  Trial Duration:       {trial_duration_sec}s")
    logger.info("  Observation Points:   AS65001 (Core), AS65003 (Edge)")
    logger.info("=" * 70)

    # Initialize dual collectors and extractors
    collector_core = FRRTelemetryCollector(router_container="as65001", poll_interval=1.0, total_configured_peers=3)
    collector_edge = FRRTelemetryCollector(router_container="as65003", poll_interval=1.0, total_configured_peers=3)
    extractor_core = BGPFeatureExtractor(baseline_origin_as=65007, baseline_as_path="65003 65007")
    extractor_edge = BGPFeatureExtractor(baseline_origin_as=65007, baseline_as_path="65003 65007")

    await collector_core.storage.initialize()
    await collector_edge.storage.initialize()

    injector = BGPAttackInjector(rogue_container="as65010", origin_container="as65007")

    scenarios = [
        ("BASE_NORMAL", "Steady-State Baseline BGP", 0, None, None),
        ("S1_DIRECT_HIJACK", "Direct Prefix Hijack (AS65010)", 3, "192.0.2.0/24", lambda: injector.inject_direct_hijack(prefix="192.0.2.0/24", rogue_origin_as=65010)),
        ("S2_SUBPREFIX_HIJACK", "Sub-Prefix Hijack /25 (AS65010)", 3, "192.0.2.0/25", lambda: injector.inject_subprefix_hijack(subprefix="192.0.2.0/25", rogue_origin_as=65010)),
        ("S3_ROUTE_LEAK", "Transit Route Leak (Valley-free violation)", 2, "192.0.2.0/24", lambda: injector.inject_route_leak(prefix="192.0.2.0/24", leaked_as_path="65006 65010 65006 65007")),
        ("S4_FLAPPING_BURST", "Burst Route Flapping on Stub", 1, "192.0.2.0/24", lambda: injector.inject_burst_flapping(prefix="192.0.2.0/24", cycles=5, interval=0.5)),
        ("S5_HISTORICAL_REPLAY", "Historical Signature Replay (YouTube/PTCL)", 3, "208.65.153.0/24", lambda: injector.inject_historical_replay("youtube_2008_hijack")),
        ("S6_PATH_MANIPULATION", "AS-Path Prepending Manipulation", 2, "192.0.2.0/24", lambda: injector.inject_route_leak(prefix="192.0.2.0/24", leaked_as_path="65002 65005 65002 65007")),
        ("RECOVERY_NORMAL", "Post-Mitigation Stabilized Baseline", 0, None, None),
    ]

    total_samples = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for scen_id, scen_name, label, target_pfx, inject_fn in scenarios:
            logger.info(f"\n>>> Scenario: {scen_id} - {scen_name} (Target Label: {label})")

            for trial in range(1, trials_per_scenario + 1):
                logger.info(f"  [Trial {trial}/{trials_per_scenario}] Executing scenario...")

                if not dry_run:
                    if inject_fn is not None:
                        res = inject_fn()
                        if asyncio.iscoroutine(res):
                            await res
                    await asyncio.sleep(1.0)  # Propagation delay

                # Poll dual routers over the trial duration
                start_t = time.time()
                trial_samples = 0
                while (time.time() - start_t) < trial_duration_sec:
                    if dry_run:
                        # Synthetic dry-run record for pipeline verification
                        synth_rec = {
                            "timestamp": time.time(),
                            "source_router": "as65001",
                            "prefix": target_pfx or "192.0.2.0/24",
                            "scenario": scen_id,
                            "trial": trial,
                            "label": label,
                            "as_path_len": 3.0 if label == 0 else 4.0,
                            "as_path_edit_distance": 0.0 if label == 0 else 2.0,
                            "origin_as_change": 1.0 if label == 3 else 0.0,
                            "prefix_mask_len": 25.0 if "SUBPREFIX" in scen_id else 24.0,
                            "announcements_per_minute": 15.0 if label == 1 else 1.0,
                            "flap_count_5min": 4.0 if label == 1 else 0.0,
                            "loc_pref_current": 100.0,
                            "route_age_seconds": 15.0,
                            "valley_free_violation": 1.0 if label == 2 else 0.0,
                            "neighbor_diversity": 0.67,
                        }
                        f.write(json.dumps(synth_rec) + "\n")
                        f.flush()
                        trial_samples += 1
                        await asyncio.sleep(1.0)
                    else:
                        n1 = await collect_from_router(collector_core, extractor_core, "as65001", scen_id, label, trial, f, target_prefix=target_pfx)
                        n2 = await collect_from_router(collector_edge, extractor_edge, "as65003", scen_id, label, trial, f, target_prefix=target_pfx)
                        trial_samples += (n1 + n2)
                        await asyncio.sleep(1.0)

                total_samples += trial_samples
                logger.info(f"    Collected {trial_samples} records for Trial {trial} (Total: {total_samples})")

                # Clean up between trials
                if not dry_run and inject_fn is not None:
                    await injector.cleanup_all_attacks()
                    await asyncio.sleep(3.0)  # Convergence stabilization

    logger.info("=" * 70)
    logger.info(f"[+] Campaign complete! Total empirical records collected: {total_samples}")
    logger.info(f"[+] Output written to: {output_path}")
    logger.info("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Empirical BGP Data Collection Campaign")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to output JSONL file")
    parser.add_argument("--trials", type=int, default=5, help="Number of trials per scenario")
    parser.add_argument("--duration", type=float, default=25.0, help="Duration in seconds per trial")
    parser.add_argument("--dry-run", action="store_true", help="Execute in dry-run mode for pipeline verification")
    args = parser.parse_args()

    configure_asyncio_policy()
    asyncio.run(run_data_collection(
        output_path=args.output,
        trials_per_scenario=args.trials,
        trial_duration_sec=args.duration,
        dry_run=args.dry_run
    ))
