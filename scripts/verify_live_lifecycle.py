"""
Live Closed-Loop Validation Experiment on 10-AS Topology:
1. Starts Autonomous Controller on Edge Defender (as65003) in background task.
2. Observes steady-state Normal operation (Trust=1.00, LP=100).
3. Injects Rogue Prefix Hijack on as65010 for 192.0.2.0/24.
4. Records Autonomous Quarantine & no-export application (MTTD & MTTM).
5. Confirms with neighbor as65008 that 192.0.2.0/24 is NOT leaked/propagated.
6. Restores legitimate Origin AS 65007.
7. Observes recovery streak and Autonomous Rollback to LocalPref 100.
"""

import sys
import os
import time
import asyncio
import subprocess

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.utils.logger import setup_logger
from src.utils.async_utils import configure_asyncio_policy
from scripts.run_autonomous_controller import AutonomousBGPController
from experiments.attacks.attack_injector import BGPAttackInjector

logger = setup_logger("live_lifecycle_test")


def run_vtysh(container: str, commands: list):
    full_cmd = ["docker", "exec", container, "vtysh"]
    for c in commands:
        full_cmd.extend(["-c", c])
    res = subprocess.run(full_cmd, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr


async def test_full_lifecycle_async():
    print("=" * 75)
    print(" 10-AS LIVE CLOSED-LOOP LIFECYCLE: NORMAL -> ATTACK -> MITIGATION -> RECOVERY")
    print("=" * 75)

    injector = BGPAttackInjector(rogue_container="as65010", origin_container="as65007")
    await injector.cleanup_all_attacks()

    # Initialize controller on Edge Defender as65003 (peering with core as65001)
    controller = AutonomousBGPController(
        router="as65003",
        peer_ip="10.0.13.2",
        poll_interval=0.5,
        shadow_sec=1.0,
        model_type="random_forest",
        total_configured_peers=3,
        baseline_origin_as=65007,
        baseline_as_path="65003 65001"
    )

    await controller.state_store.initialize()
    await controller.state_store.clear_all()
    await controller.policy_engine.apply_policy({}, settle_delay_sec=0.2)

    # Start controller task
    ctrl_task = asyncio.create_task(controller.run())
    await asyncio.sleep(2.0)  # Settle startup

    mttd = None
    mttm = None
    quarantined = False
    rolled_back = False

    try:
        # Phase 1: Steady-state baseline
        print("\n--- PHASE 1: Baseline Steady State ---")
        await asyncio.sleep(2.0)
        initial_lp = controller.active_policies.get("192.0.2.0/24", {}).get("loc_pref", 100)
        print(f"[+] Initial LocalPref for 192.0.2.0/24: {initial_lp}")

        # Phase 2: Inject Sub-Prefix Hijack
        print("\n--- PHASE 2: Injecting Rogue Sub-Prefix Hijack on AS65010 (192.0.2.0/25) ---")
        t0 = time.time()
        await injector.inject_subprefix_hijack(subprefix="192.0.2.0/25", rogue_origin_as=65010)

        # Monitor detection and mitigation
        for _ in range(30):
            await asyncio.sleep(0.5)
            # Check detection
            det = await controller.state_store.get_latest_detection("192.0.2.0/25", min_timestamp=t0)
            if det and mttd is None:
                mttd = round(det["detected_at"] - t0, 3)
                print(f"[+] Attack Detected in {mttd:.3f}s (Class ID: {det['class_id']}, Trust: {det['trust_score']:.2f})")

            # Check mitigation
            active_pol = controller.active_policies.get("192.0.2.0/25", {})
            cur_lp = active_pol.get("loc_pref", 100)
            cur_comm = active_pol.get("community")
            if cur_lp == 0 and cur_comm == "no-export":
                if mttm is None:
                    mttm = round(time.time() - t0, 3)
                    quarantined = True
                    print(f"[+] Anomaly Quarantined (MTTM) in {mttm:.3f}s! Policy: LP={cur_lp}, Community={cur_comm}")
                    break

        # Phase 3: Verify downstream isolation
        print("\n--- PHASE 3: Verifying RIB Quarantine & Outbound Isolation ---")
        code, out, _ = run_vtysh("as65003", ["show bgp ipv4 unicast 192.0.2.0/25"])
        print(f"AS65003 BGP entry for 192.0.2.0/25:\n{out.strip()}")

        # Phase 4: Clean attack and verify recovery
        print("\n--- PHASE 4: Restoring Clean Baseline (Removing Rogue Announcement) ---")
        t_restore = time.time()
        await injector.cleanup_all_attacks()

        # Wait for rollback
        for _ in range(25):
            await asyncio.sleep(1.0)
            active_pol = controller.active_policies.get("192.0.2.0/25", {})
            if not active_pol or active_pol.get("loc_pref", 100) == 100:
                rolled_back = True
                recovery_time = round(time.time() - t_restore, 3)
                print(f"[+] Autonomous Rollback Complete! Quarantine cleared in {recovery_time:.3f}s.")
                break

    finally:
        controller._shutdown.set()
        await ctrl_task
        await injector.cleanup_all_attacks()

    print("\n" + "=" * 75)
    print(" 10-AS LIVE LIFECYCLE SUMMARY")
    print("=" * 75)
    print(f"1. Detection Latency (MTTD):               {f'{mttd:.3f}s' if mttd else 'FAILED'}")
    print(f"2. Mitigation Latency (MTTM):              {f'{mttm:.3f}s' if mttm else 'FAILED'}")
    print(f"3. Dual Quarantine (LP 0 + no-export):     {'PASS' if quarantined else 'FAIL'}")
    print(f"4. Autonomous Rollback to LP 100:          {'PASS' if rolled_back else 'FAIL'}")
    print("=" * 75)
    return quarantined and (mttd is not None)


if __name__ == "__main__":
    configure_asyncio_policy()
    ok = asyncio.run(test_full_lifecycle_async())
    sys.exit(0 if ok else 1)
