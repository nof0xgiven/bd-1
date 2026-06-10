import re

import pytest

from bd1.config import default_workspace_config
from bd1.errors import WorkspaceConfigError
from bd1.models import (
    AttemptRecord,
    FeedbackRecord,
    LearningRecord,
    RunRecord,
    RunState,
    WorkspaceConfig,
)
from bd1.paths import global_state_dir, make_run_id, slugify


def test_global_state_dir_resolves_relative_bd1_home(monkeypatch):
    monkeypatch.setenv("BD1_HOME", "relative-state-dir")

    assert global_state_dir().is_absolute()


def test_slugify_and_run_id_are_stable():
    assert slugify("Add billing webhook retry!") == "add-billing-webhook-retry"
    assert make_run_id("Fix API drift", now="2026-06-09T12:34:56Z", suffix="ab12") == (
        "run-20260609T123456Z-fix-api-drift-ab12"
    )


def test_make_run_id_normalizes_offset_timestamps_to_utc():
    assert make_run_id("Fix API drift", now="2026-06-09T12:34:56+02:00", suffix="ab12") == (
        "run-20260609T103456Z-fix-api-drift-ab12"
    )


def test_make_run_id_appends_random_suffix_by_default():
    run_id = make_run_id("Fix API drift", now="2026-06-09T12:34:56Z")

    assert re.fullmatch(r"run-20260609T123456Z-fix-api-drift-[0-9a-f]{4}", run_id)


def test_workspace_config_round_trips():
    config = WorkspaceConfig(
        name="demo",
        repo_path="/repo",
        default_branch="main",
        product_description="Demo",
        setup_script="scripts/setup.sh",
        max_attempts=5,
        pi_command="pi",
        pi_model="",
        pi_provider="",
        vet_command="vet",
        vet_model="flash",
        vet_confidence_threshold=0.8,
        dspy_model="openai/gpt-5-mini",
        dirty_exit_prompt="commit and resolve before exit",
    )

    assert WorkspaceConfig.from_dict(config.to_dict()) == config


def test_workspace_config_rejects_unknown_keys():
    config = default_workspace_config("demo", "/repo", "Demo")

    with pytest.raises(WorkspaceConfigError) as exc:
        WorkspaceConfig.from_dict({**config.to_dict(), "artifact_policy": "curated"})

    assert "artifact_policy" in str(exc.value)


def test_workspace_config_rejects_missing_required_keys():
    with pytest.raises(WorkspaceConfigError) as exc:
        WorkspaceConfig.from_dict({"name": "x"})

    assert "missing required key(s)" in str(exc.value)


def test_workspace_config_preserves_pr_lifecycle_fields():
    config = default_workspace_config("demo", "/tmp/repo", "Demo")

    assert config.pr_command == "gh"
    assert config.pr_monitor_wait_seconds == 600
    assert config.max_pr_feedback_attempts == 3
    assert config.max_pr_monitor_polls == 6
    assert config.pr_base_branch == ""
    assert config.pr_draft is False
    assert config.pr_comment_ignore_authors == []

    restored = WorkspaceConfig.from_dict(config.to_dict())

    assert restored == config


def test_workspace_config_has_reasoning_reliability_knobs():
    config = default_workspace_config(
        name="demo", repo_path="/tmp/demo", product_description="demo product"
    )
    assert config.dspy_num_retries == 3
    assert config.discovery_max_iters == 12


def test_workspace_config_rejects_negative_dspy_num_retries():
    config = default_workspace_config("demo", "/repo", "Demo")

    with pytest.raises(WorkspaceConfigError) as exc:
        WorkspaceConfig.from_dict({**config.to_dict(), "dspy_num_retries": -1})

    assert "dspy_num_retries" in str(exc.value)


def test_workspace_config_rejects_zero_discovery_max_iters():
    config = default_workspace_config("demo", "/repo", "Demo")

    with pytest.raises(WorkspaceConfigError) as exc:
        WorkspaceConfig.from_dict({**config.to_dict(), "discovery_max_iters": 0})

    assert "discovery_max_iters" in str(exc.value)


def test_run_record_preserves_typed_nested_records():
    attempt = AttemptRecord(
        number=1,
        pi_session_id="session-1",
        pi_session_file=".sessions/run/attempt/session.jsonl",
        pi_stdout_path=".sessions/run/attempt/pi-stdout.txt",
        pi_stderr_path=".sessions/run/attempt/pi-stderr.txt",
        git_diff_path=".sessions/run/attempt/git-diff.patch",
        commit_sha="abc123",
        vet_command="vet Fix --model flash",
        vet_exit_code=0,
        vet_output_path=".artifacts/vet/fix-1.json",
        review_path=".artifacts/reviews/fix-1-pass.md",
        review_verdict="PASS",
        state_transition_reason="Vet and review passed",
    )
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="Fix bug",
        base_commit="base",
        branch="bd-1/run-1",
        worktree="/worktree",
        state=RunState.COMPLETE,
        created_at="2026-06-09T12:00:00Z",
        updated_at="2026-06-09T12:01:00Z",
        artifacts={"plan": ".artifacts/plans/fix.md"},
        attempts=[attempt],
        final_verdict="PASS",
        blocker_path="",
        feedback_paths=[],
    )

    restored = RunRecord.from_dict(record.to_dict())

    assert restored == record
    assert restored.state is RunState.COMPLETE
    assert restored.attempts[0] == attempt


def test_run_record_preserves_pr_metadata_fields():
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="Fix bug",
        base_commit="abc123",
        branch="bd-1/run-1",
        worktree="/tmp/worktree",
        state=RunState.PR_READY,
        created_at="2026-06-09T00:00:00Z",
        updated_at="2026-06-09T00:00:01Z",
        pr_number=42,
        pr_url="https://github.com/acme/demo/pull/42",
        pr_feedback_paths=[".artifacts/pr/fix-bug-1.md"],
        pr_complete_path=".artifacts/pr/fix-bug-1-complete.md",
        pr_seen_feedback_keys=["ci:pytest", "review:123"],
    )

    restored = RunRecord.from_dict(record.to_dict())

    assert restored == record


def test_run_record_round_trips_merge_synced_at():
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="Fix bug",
        base_commit="abc123",
        branch="bd-1/run-1",
        worktree="/tmp/worktree",
        state=RunState.COMPLETE,
        created_at="2026-06-10T00:00:00Z",
        updated_at="2026-06-10T00:00:01Z",
        merge_synced_at="2026-06-10T12:00:00Z",
    )

    assert RunRecord.from_dict(record.to_dict()).merge_synced_at == "2026-06-10T12:00:00Z"
    assert RunRecord.from_dict({**record.to_dict(), "merge_synced_at": ""}).merge_synced_at == ""
    # backward compat: old records lack the key entirely
    data = record.to_dict()
    data.pop("merge_synced_at")
    assert RunRecord.from_dict(data).merge_synced_at == ""


def test_run_record_loads_existing_files_without_pr_fields():
    record = RunRecord.from_dict(
        {
            "run_id": "run-1",
            "workspace": "demo",
            "task": "Fix bug",
            "base_commit": "abc123",
            "branch": "bd-1/run-1",
            "worktree": "/tmp/worktree",
            "state": "COMPLETE",
            "created_at": "2026-06-09T00:00:00Z",
            "updated_at": "2026-06-09T00:00:01Z",
        }
    )

    assert record.pr_number is None
    assert record.pr_url == ""
    assert record.pr_feedback_paths == []
    assert record.pr_complete_path == ""
    assert record.pr_seen_feedback_keys == []


def test_feedback_and_learning_records_round_trip():
    feedback = FeedbackRecord(
        run_id="run-1",
        created_at="2026-06-09T12:00:00Z",
        outcome="wrong_behavior",
        wrong_or_missing="Plan missed tests",
        expected="Plan includes integration test",
        affected_artifact=".artifacts/plans/fix.md",
        commit="abc123",
        learning_candidate=True,
    )
    learning = LearningRecord(
        id="learning-1",
        created_at="2026-06-09T12:00:00Z",
        status="active",
        source_run_id="run-1",
        source_task="Fix bug",
        category="testing_pattern",
        applies_when="Changing API behavior",
        rule="Test the request boundary",
        rationale="Unit tests missed route wiring",
        evidence=[{"artifact": ".artifacts/reviews/fix.md", "excerpt": "Route not tested"}],
        tags=["api", "testing"],
        confidence=0.9,
    )

    assert FeedbackRecord.from_dict(feedback.to_dict()) == feedback
    assert LearningRecord.from_dict(learning.to_dict()) == learning
