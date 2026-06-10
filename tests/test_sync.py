from __future__ import annotations

import json
import types

import pytest

from bd1.config import default_workspace_config
from bd1.dspy_programs import TemplateReasoningPrograms
from bd1.learning import LearningStore
from bd1.models import RunRecord, RunState
from bd1.run_store import RunStore
from bd1.sync import SyncOutcome, sync_runs


def _result(exit_code: int, stdout: str, stderr: str = ""):
    return types.SimpleNamespace(exit_code=exit_code, stdout=stdout, stderr=stderr)


def _gh_view_response(state: str, merged_at: str = "") -> str:
    return json.dumps({"state": state, "mergedAt": merged_at})


@pytest.fixture()
def complete_run_record(tmp_path):
    """A COMPLETE, archived run (worktree already cleaned) with PR #7."""
    state = tmp_path / "state"
    run_store = RunStore(state)
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="add feature",
        base_commit="abc",
        branch="bd-1/run-1",
        worktree=str(tmp_path / "gone-worktree"),
        state=RunState.COMPLETE,
        created_at="2026-06-10T00:00:00Z",
        updated_at="2026-06-10T00:00:00Z",
        final_verdict="PASS",
        pr_number=7,
    )
    run_store.write_archived(record)
    archive = run_store.archive_dir("run-1")
    (archive / "final-diff.patch").write_text("diff text", encoding="utf-8")
    (archive / "review.md").write_text("review text", encoding="utf-8")
    (archive / "pr-feedback-001.md").write_text("feedback", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    config = default_workspace_config(name="demo", repo_path=str(repo), product_description="demo")
    return record, run_store, config


def test_sync_learns_from_merged_pr_and_marks_record(tmp_path, complete_run_record):
    record, run_store, config = complete_run_record

    def runner(command, *, cwd, env=None, timeout=None):
        assert command[:3] == ["gh", "pr", "view"]
        return _result(0, _gh_view_response("MERGED", "2026-06-10T10:00:00Z"))

    outcome = sync_runs(
        run_store=run_store,
        records=[record],
        config=config,
        reasoning=TemplateReasoningPrograms(),
        runner=runner,
        global_root=run_store.global_root,
    )
    assert isinstance(outcome, SyncOutcome)
    assert outcome.learned == [record.run_id]
    updated = run_store.read_by_id(record.run_id)
    assert updated.merge_synced_at != ""
    store = LearningStore.for_workspace(run_store.global_root, record.workspace)
    assert store.load_learnings()  # the merge learning was persisted


def test_sync_skips_unmerged_and_already_synced(tmp_path, complete_run_record):
    record, run_store, config = complete_run_record

    def runner(command, *, cwd, env=None, timeout=None):
        return _result(0, _gh_view_response("OPEN"))

    outcome = sync_runs(
        run_store=run_store,
        records=[record],
        config=config,
        reasoning=TemplateReasoningPrograms(),
        runner=runner,
        global_root=run_store.global_root,
    )
    assert outcome.learned == []
    assert outcome.skipped == {record.run_id: "not merged (OPEN)"}


def test_sync_ignores_ineligible_records(tmp_path, complete_run_record):
    from dataclasses import replace

    record, run_store, config = complete_run_record
    already_synced = replace(record, merge_synced_at="2026-06-10T11:00:00Z")
    no_pr = replace(record, run_id="run-2", pr_number=None)
    not_complete = replace(record, run_id="run-3", state=RunState.PR_READY)

    def runner(command, *, cwd, env=None, timeout=None):  # pragma: no cover - never called
        raise AssertionError("gh should not be invoked for ineligible records")

    outcome = sync_runs(
        run_store=run_store,
        records=[already_synced, no_pr, not_complete],
        config=config,
        reasoning=TemplateReasoningPrograms(),
        runner=runner,
        global_root=run_store.global_root,
    )
    assert outcome.checked == 0
    assert outcome.learned == []
    assert outcome.skipped == {}


def test_sync_inlines_archived_run_context_into_learning(tmp_path, complete_run_record):
    record, run_store, config = complete_run_record
    archive = run_store.archive_dir("run-1")
    (archive / "discovery-context.md").write_text("DISCOVERY-CONTENT", encoding="utf-8")
    (archive / "pi-session.jsonl").write_text('{"role": "user"}', encoding="utf-8")

    class _RecordingLearn(TemplateReasoningPrograms):
        def __init__(self):
            self.evidence_seen = None

        def learn(self, evidence, *, review_markdown, final_diff="", pr_feedback=""):
            self.evidence_seen = evidence
            return super().learn(
                evidence,
                review_markdown=review_markdown,
                final_diff=final_diff,
                pr_feedback=pr_feedback,
            )

    reasoning = _RecordingLearn()

    def runner(command, *, cwd, env=None, timeout=None):
        return _result(0, _gh_view_response("MERGED", "2026-06-10T10:00:00Z"))

    sync_runs(
        run_store=run_store,
        records=[record],
        config=config,
        reasoning=reasoning,
        runner=runner,
        global_root=run_store.global_root,
    )
    assert "DISCOVERY-CONTENT" in reasoning.evidence_seen.extra_context
    assert "pi-session.jsonl" in reasoning.evidence_seen.extra_context


def test_sync_tolerates_gh_failure_per_record(tmp_path, complete_run_record):
    record, run_store, config = complete_run_record

    def runner(command, *, cwd, env=None, timeout=None):
        return _result(1, "", stderr="boom")

    outcome = sync_runs(
        run_store=run_store,
        records=[record],
        config=config,
        reasoning=TemplateReasoningPrograms(),
        runner=runner,
        global_root=run_store.global_root,
    )
    assert record.run_id in outcome.skipped
    assert outcome.learned == []
    # record stays eligible for the next sweep
    assert run_store.read_by_id(record.run_id).merge_synced_at == ""
