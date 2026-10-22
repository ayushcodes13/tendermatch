from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tender_pipeline_queues_pending_runs_in_order():
    workflow = (ROOT / ".github/workflows/tender_pipeline.yml").read_text(encoding="utf-8")
    concurrency = workflow.split("concurrency:", 1)[1].split("jobs:", 1)[0]

    assert "group: tender-pipeline" in concurrency
    assert "cancel-in-progress: false" in concurrency
    assert "queue: max" in concurrency
