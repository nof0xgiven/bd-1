from bd1.models import (
    AttemptRecord,
    FeedbackRecord,
    LearningRecord,
    RunRecord,
    RunState,
    WorkspaceConfig,
)
from bd1.paths import make_run_id, slugify


def test_slugify_and_run_id_are_stable():
    assert slugify("Add billing webhook retry!") == "add-billing-webhook-retry"
    assert make_run_id("Fix API drift", now="2026-06-09T12:34:56Z") == (
        "run-20260609T123456Z-fix-api-drift"
    )


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
        artifact_policy="curated",
        dirty_base_policy="fail_fast",
        require_clean_committed_attempt=True,
        dirty_exit_prompt="commit and resolve before exit",
        worktree_root_policy="global",
    )

    assert WorkspaceConfig.from_dict(config.to_dict()) == config


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
