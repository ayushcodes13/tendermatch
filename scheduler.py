import time
import traceback

from pipeline.run import run_pipeline


INTERVAL = 30 * 60  # 30 minutes


def start_scheduler():
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