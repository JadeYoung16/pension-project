"""
ONCAP Synthetic Data — master orchestrator.

Runs all upstream simulators in dependency order:

  Stage 1: Employer Registry              (uses CRA T3010 ident + Schedule 3)
  Stage 2: Member Census                  (depends on Stage 1)
  Stage 3a: Transactions                  (depends on Stage 2)
  Stage 3b: Life Events (buyback)         (depends on Stage 2)
  Stage 3c: Portal Events                 (depends on Stage 2)
  Stage 3d: Call Logs                     (depends on Stage 2)
  Stage 3e: Seminar Attendance            (depends on Stage 2)
  Stage 3f: Email Engagement              (depends on Stage 2)

Usage:
    python -m upstream_simulators.run_all
    python -m upstream_simulators.run_all --skip-stage 1
    python -m upstream_simulators.run_all --only-stage 3b
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from upstream_simulators.generators import employer_generator
from upstream_simulators.generators import member_generator
from upstream_simulators.generators import transaction_generator
from upstream_simulators.generators import life_event_generator
from upstream_simulators.generators import portal_event_generator
from upstream_simulators.generators import call_log_generator
from upstream_simulators.generators import seminar_generator
from upstream_simulators.generators import email_engagement_generator


STAGES = [
    ("1", "Employer Registry", employer_generator),
    ("2", "Member Census", member_generator),
    ("3a", "Transactions", transaction_generator),
    ("3b", "Life Events (buyback)", life_event_generator),
    ("3c", "Portal Events", portal_event_generator),
    ("3d", "Call Logs", call_log_generator),
    ("3e", "Seminar Attendance", seminar_generator),
    ("3f", "Email Engagement", email_engagement_generator),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all ONCAP synthetic data generators.")
    parser.add_argument("--skip-stage", action="append", default=[],
                        help="Skip a stage by id (e.g. --skip-stage 1)")
    parser.add_argument("--only-stage", default=None,
                        help="Run only the named stage (e.g. --only-stage 3b)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level, format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 70)
    print("ONCAP Synthetic Data — Full Pipeline")
    print("=" * 70)

    overall_start = time.time()
    failures = []

    for stage_id, stage_name, module in STAGES:
        if args.only_stage and args.only_stage != stage_id:
            continue
        if stage_id in args.skip_stage:
            print(f"\n[SKIPPED] Stage {stage_id}: {stage_name}")
            continue

        print(f"\n>>> Stage {stage_id}: {stage_name}")
        print("-" * 70)
        start = time.time()
        try:
            old_argv = sys.argv
            sys.argv = [module.__name__]
            rc = module.main()
            sys.argv = old_argv
            elapsed = time.time() - start
            if rc == 0:
                print(f"\n  Stage {stage_id} completed in {elapsed:.1f}s")
            else:
                print(f"\n  Stage {stage_id} returned non-zero ({rc})")
                failures.append(stage_id)
        except Exception as e:
            elapsed = time.time() - start
            print(f"\n  Stage {stage_id} crashed after {elapsed:.1f}s: {e}")
            import traceback
            traceback.print_exc()
            failures.append(stage_id)

    overall_elapsed = time.time() - overall_start
    print()
    print("=" * 70)
    if failures:
        print(f"DONE WITH ERRORS in {overall_elapsed:.1f}s. Failed: {failures}")
    else:
        print(f"ALL STAGES COMPLETED in {overall_elapsed:.1f}s.")
    print("=" * 70)

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
