"""CLI orchestrator: extract -> transform -> validate.

    python -m warehouse.pipeline [--skip-extract] [--only-validate] [--step STEP] [--dry-run]

Same shape as the sibling Porto project's pipeline.py: a steps list,
critical-step-abort, an audit log row per step, --dry-run with zero side
effects.
"""
import argparse
import sys
import traceback
import uuid
from datetime import datetime

from warehouse import db, extract, transform, validate

STEPS = ["extract", "transform", "validate"]
CRITICAL_STEPS = {"extract"}


def _log_run(con, run_id, step, status, start, error_message=None):
    con.execute(
        """INSERT INTO audit.pipeline_runs (run_id, step, start_time, end_time, status, error_message)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [run_id, step, start, datetime.now(), status, error_message],
    )


def determine_steps(skip_extract=False, only_validate=False, only_step=None):
    if only_step:
        return [only_step]
    if only_validate:
        return ["validate"]
    steps = list(STEPS)
    if skip_extract:
        steps.remove("extract")
    return steps


def run(skip_extract=False, only_validate=False, only_step=None, dry_run=False):
    run_id = str(uuid.uuid4())
    steps = determine_steps(skip_extract, only_validate, only_step)
    con = db.get_target_connection()
    failed = False
    validation_passed = True

    print(f"=== PIPELINE RUN {run_id} | steps={steps} ===")
    try:
        for step in steps:
            start = datetime.now()
            print(f"\n--- STEP: {step} ---")
            if dry_run:
                print(f"    [DRY-RUN] would run {step}")
                _log_run(con, run_id, step, "DRY_RUN", start)
                continue
            try:
                if step == "extract":
                    extract.run(con=con)
                elif step == "transform":
                    transform.run(con=con)
                elif step == "validate":
                    validation_passed = validate.run(con=con, run_id=run_id)
                _log_run(con, run_id, step, "SUCCESS", start)
            except Exception as e:
                traceback.print_exc()
                _log_run(con, run_id, step, "FAILED", start, error_message=str(e))
                failed = True
                if step in CRITICAL_STEPS:
                    print(f"[ABORT] {step} failed and is critical -- stopping")
                    break
    finally:
        con.close()

    ok = not failed and validation_passed
    print(f"\n=== {'DONE' if ok else 'FAILED'} ({run_id}) ===")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Run the TerraPath migration pipeline")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--only-validate", action="store_true")
    parser.add_argument("--step", choices=STEPS, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ok = run(
        skip_extract=args.skip_extract, only_validate=args.only_validate,
        only_step=args.step, dry_run=args.dry_run,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
