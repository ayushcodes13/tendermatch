from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_tender_pipeline_queues_pending_runs_in_order():
    workflow = (ROOT / ".github/workflows/tender_pipeline.yml").read_text(encoding="utf-8")
    concurrency = workflow.split("concurrency:", 1)[1].split("jobs:", 1)[0]

    assert "group: tender-pipeline" in concurrency
    assert "cancel-in-progress: false" in concurrency
    assert "queue: max" in concurrency


def test_tender_pipeline_token_has_only_read_access_to_repository_contents():
    workflow = (ROOT / ".github/workflows/tender_pipeline.yml").read_text(encoding="utf-8")
    permissions = workflow.split("permissions:", 1)[1].split("concurrency:", 1)[0]

    assert "contents: read" in permissions
    assert "contents: write" not in permissions


def test_github_actions_dependencies_use_full_commit_shas():
    for workflow_path in (ROOT / ".github/workflows").glob("*.yml"):
        workflow = workflow_path.read_text(encoding="utf-8")
        action_references = re.findall(r"^\s+uses:\s+([^\s]+)", workflow, flags=re.MULTILINE)

        assert action_references, f"No actions found in {workflow_path.name}"
        assert all(
            re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}", reference)
            for reference in action_references
        ), f"Workflow actions must use immutable 40-character commit SHAs: {workflow_path.name}"
