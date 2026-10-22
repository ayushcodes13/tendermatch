"""
Background execution manager for the tender intelligence pipeline.

Pipeline role:
Ensures the pipeline runs at regular intervals to capture new tenders in near 
real-time. Acts as the entry point for production deployments.

Key responsibilities:
- Managing the infinite execution loop.
- Handling top-level exceptions to prevent the process from crashing.
- Coordinating sleep intervals between consecutive pipeline runs.

Notes:
- Default interval is 30 minutes, configurable via global constants.
- Failure logs retain exception types without printing raw exception payloads.
"""
import os
import time

from data.backup import is_maintenance_active
from pipeline.run import run_pipeline


INTERVAL = 30 * 60  # 30 minutes


def run_scheduler_step():
    """Run a single scheduler step if no database maintenance is active."""
    configured_path = os.environ.get("TENDERMATCH_DB_PATH") or "data/tenders.db"
    if is_maintenance_active(configured_path):
        print(f"⚠️ Maintenance in progress on {configured_path}; pausing scheduled run.")
        return False
    print("\n⏱ Running pipeline...")
    run_pipeline()
    print("✅ Run complete.")
    return True


def start_scheduler():
    """
    Starts the infinite loop for periodic pipeline execution.

    Side Effects:
        - Logs pipeline status to stdout.
        - Triggers run_scheduler_step() every INTERVAL seconds.
    """
    print("🚀 Scheduler started...")

    while True:
        try:
            run_scheduler_step()
        except Exception as e:
            # Avoid tracebacks and exception payloads that may expose secrets.
            print(f"❌ Pipeline run failed ({type(e).__name__}).")

        print(f"😴 Sleeping for {INTERVAL/60} minutes...\n")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    start_scheduler()
