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
import time

from pipeline.run import run_pipeline


INTERVAL = 30 * 60  # 30 minutes


def start_scheduler():
    """
    Starts the infinite loop for periodic pipeline execution.

    Side Effects:
        - Logs pipeline status to stdout.
        - Triggers the full run_pipeline() logic every INTERVAL seconds.
    """
    print("🚀 Scheduler started...")

    while True:
        try:
            print("\n⏱ Running pipeline...")
            run_pipeline()
            print("✅ Run complete.")

        except Exception as e:
            # Avoid tracebacks and exception payloads that may expose secrets.
            print(f"❌ Pipeline run failed ({type(e).__name__}).")

        print(f"😴 Sleeping for {INTERVAL/60} minutes...\n")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    start_scheduler()
