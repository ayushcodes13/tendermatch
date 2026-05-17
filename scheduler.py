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
- Error logs include full tracebacks for debugging pipeline failures.
"""
import time
import traceback

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
            print("❌ Error occurred:")
            traceback.print_exc()

        print(f"😴 Sleeping for {INTERVAL/60} minutes...\n")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    start_scheduler()