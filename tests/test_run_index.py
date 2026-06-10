import json
import shutil
from dataclasses import replace

import pytest

from bd1.errors import IllegalTransitionError, UnknownRunError
from bd1.models import AttemptRecord, RunRecord, RunState
from bd1.run_index import RunIndex
from bd1.run_store import RunStore


def make_run() -> RunRecord:
    return RunRecord(
        run_id="run-1",
        workspace="demo",
        task="Fix bug",
        base_commit="abc",
        branch="bd-1/run-1",
        worktree="/tmp/worktree",
        state=RunState.TASK_RECEIVED,
        created_at="2026-06-09T12:00:00Z",
        updated_at="2026-06-09T12:00:00Z",
    )


def make_attempt() -> AttemptRecord:
    return AttemptRecord(
        number=1,
        pi_session_id="session-1",
        pi_session_file=".sessions/run-1/attempt-1/session.jsonl",
        pi_stdout_path=".sessions/run-1/attempt-1/pi-stdout.txt",
        pi_stderr_path=".sessions/run-1/attempt-1/pi-stderr.txt",
        git_diff_path=".sessions/run-1/attempt-1/git-diff.patch",
        commit_sha="def",
        vet_command="vet task --model flash",
        vet_exit_code=0,
        vet_output_path=".sessions/run-1/attempt-1/vet.txt",
        review_path=".sessions/run-1/attempt-1/review.md",
        review_verdict="passed",
        state_transition_reason="Vet and review passed",
    )


def test_run_store_persists_authoritative_record_and_global_pointer(tmp_path):
    store = RunStore(global_root=tmp_path / "global")
    repo = tmp_path / "repo"
    repo.mkdir()
    record = make_run()

    path = store.write(repo, record)

    assert path == repo / ".sessions" / "run-1" / "run-record.json"
    assert store.read_by_id("run-1") == record


def test_run_store_preserves_nested_attempt_records(tmp_path):
    store = RunStore(global_root=tmp_path / "global")
    repo = tmp_path / "repo"
    repo.mkdir()
    record = replace(make_run(), attempts=[make_attempt()])

    store.write(repo, record)

    restored = store.read_by_id("run-1")
    assert restored == record
    assert isinstance(restored.attempts[0], AttemptRecord)


def test_transition_updates_state_and_timestamp(tmp_path):
    store = RunStore(global_root=tmp_path / "global")
    repo = tmp_path / "repo"
    repo.mkdir()
    record = make_run()
    store.write(repo, record)

    updated = store.transition(repo, record, RunState.BASE_VERIFIED, "base clean")

    assert updated.state is RunState.BASE_VERIFIED
    assert updated.updated_at >= record.updated_at
    assert store.read_by_id("run-1").state is RunState.BASE_VERIFIED


def test_index_rebuilds_from_authoritative_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RunStore(global_root=tmp_path / "global")
    store.write(repo, make_run())
    index = RunIndex(tmp_path / "runs.db")

    index.rebuild_from_workspace(repo)

    assert index.get_run("run-1") == make_run()


def test_index_preserves_nested_attempt_records(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RunStore(global_root=tmp_path / "global")
    record = replace(make_run(), attempts=[make_attempt()])
    store.write(repo, record)
    index = RunIndex(tmp_path / "runs.db")

    index.rebuild_from_workspace(repo)

    restored = index.get_run("run-1")
    assert restored == record
    assert isinstance(restored.attempts[0], AttemptRecord)


def test_transition_rejects_illegal_jump(tmp_path):
    store = RunStore(global_root=tmp_path / "global")
    repo = tmp_path / "repo"
    repo.mkdir()
    record = make_run()
    store.write(repo, record)

    with pytest.raises(IllegalTransitionError) as exc:
        store.transition(repo, record, RunState.COMPLETE, "skipping ahead")

    assert "TASK_RECEIVED -> COMPLETE" in str(exc.value)
    assert store.read_by_id("run-1").state is RunState.TASK_RECEIVED


def test_transition_rejects_leaving_terminal_states(tmp_path):
    store = RunStore(global_root=tmp_path / "global")
    repo = tmp_path / "repo"
    repo.mkdir()
    record = replace(make_run(), state=RunState.COMPLETE)
    store.write(repo, record)

    with pytest.raises(IllegalTransitionError):
        store.transition(repo, record, RunState.BLOCKED, "no way back")


def test_read_by_id_unknown_run_raises_friendly_error(tmp_path):
    store = RunStore(global_root=tmp_path / "global")

    with pytest.raises(UnknownRunError) as exc:
        store.read_by_id("run-missing")

    assert "Unknown run id: run-missing" in str(exc.value)


def test_read_by_id_falls_back_to_archive_when_worktree_pruned(tmp_path):
    store = RunStore(global_root=tmp_path / "global")
    repo = tmp_path / "repo"
    repo.mkdir()
    record = replace(make_run(), worktree=str(repo), state=RunState.COMPLETE)
    store.write(repo, record)
    store.archive(record)
    shutil.rmtree(repo)

    assert store.read_by_id("run-1") == record


def test_read_by_id_without_archive_raises_friendly_error(tmp_path):
    store = RunStore(global_root=tmp_path / "global")
    repo = tmp_path / "repo"
    repo.mkdir()
    store.write(repo, make_run())
    shutil.rmtree(repo)

    with pytest.raises(UnknownRunError) as exc:
        store.read_by_id("run-1")

    assert "worktree may have been removed" in str(exc.value)


def test_archive_copies_record_and_transitions(tmp_path):
    store = RunStore(global_root=tmp_path / "global")
    repo = tmp_path / "repo"
    repo.mkdir()
    record = replace(make_run(), worktree=str(repo))
    store.write(repo, record)
    record = store.transition(repo, record, RunState.BASE_VERIFIED, "base clean")

    archived_path = store.archive(record)

    archive_dir = tmp_path / "global" / "runs" / "run-1"
    assert archived_path == archive_dir / "run-record.json"
    assert (archive_dir / "transitions.jsonl").exists()
    assert store.read(archived_path) == record


def _learning_attempt(
    diff_path: str,
    review_path: str,
    session_file: str = "",
    stdout_path: str = "",
    stderr_path: str = "",
    vet_output_path: str = "",
) -> AttemptRecord:
    return AttemptRecord(
        number=1,
        pi_session_id="s",
        pi_session_file=session_file or "f",
        pi_stdout_path=stdout_path or "o",
        pi_stderr_path=stderr_path or "e",
        git_diff_path=diff_path,
        commit_sha="abc",
        vet_command="vet",
        vet_exit_code=0,
        vet_output_path=vet_output_path or "v",
        review_path=review_path,
        review_verdict="PASS",
        state_transition_reason="reason",
    )


def test_archive_copies_learning_inputs(tmp_path):
    worktree = tmp_path / "wt"
    session_dir = worktree / ".sessions" / "run-1"
    session_dir.mkdir(parents=True)
    diff_path = worktree / "diff.patch"
    diff_path.write_text("diff text", encoding="utf-8")
    review_path = worktree / "review.md"
    review_path.write_text("review text", encoding="utf-8")
    session_file = worktree / "session.jsonl"
    session_file.write_text('{"role":"user"}\n', encoding="utf-8")
    stdout_path = worktree / "pi-out.txt"
    stdout_path.write_text("out", encoding="utf-8")
    stderr_path = worktree / "pi-err.txt"
    stderr_path.write_text("err", encoding="utf-8")
    vet_out = worktree / "vet.json"
    vet_out.write_text("{}", encoding="utf-8")
    feedback_path = worktree / "pr-feedback.md"
    feedback_path.write_text("feedback", encoding="utf-8")
    discovery = worktree / "discovery.md"
    discovery.write_text("ctx", encoding="utf-8")
    plan = worktree / "plan.md"
    plan.write_text("plan", encoding="utf-8")
    completed = worktree / "completed.md"
    completed.write_text("done", encoding="utf-8")
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="t",
        base_commit="abc",
        branch="bd-1/run-1",
        worktree=str(worktree),
        state=RunState.COMPLETE,
        created_at="2026-06-10T00:00:00Z",
        updated_at="2026-06-10T00:00:00Z",
        attempts=[
            _learning_attempt(
                str(diff_path),
                str(review_path),
                str(session_file),
                str(stdout_path),
                str(stderr_path),
                str(vet_out),
            )
        ],
        pr_number=7,
        pr_feedback_paths=[str(feedback_path)],
        artifacts={
            "discovery_context": str(discovery),
            "plan": str(plan),
            "completed": str(completed),
        },
    )
    (session_dir / "run-record.json").write_text(json.dumps(record.to_dict()), encoding="utf-8")
    run_store = RunStore(tmp_path / "state")

    run_store.archive(record)

    archive = run_store.archive_dir(record.run_id)
    assert (archive / "final-diff.patch").read_text(encoding="utf-8") == "diff text"
    assert (archive / "review.md").read_text(encoding="utf-8") == "review text"
    assert (archive / "pi-session.jsonl").exists()
    assert (archive / "pi-stdout.txt").exists()
    assert (archive / "pi-stderr.txt").exists()
    assert (archive / "vet-output.json").exists()
    assert (archive / "discovery-context.md").read_text(encoding="utf-8") == "ctx"
    assert (archive / "plan.md").exists()
    assert (archive / "completed.md").exists()
    assert (archive / "pr-feedback-001.md").exists()


def test_archive_skips_relative_or_missing_learning_inputs(tmp_path):
    worktree = tmp_path / "wt"
    session_dir = worktree / ".sessions" / "run-1"
    session_dir.mkdir(parents=True)
    missing = worktree / "gone.patch"
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="t",
        base_commit="abc",
        branch="bd-1/run-1",
        worktree=str(worktree),
        state=RunState.COMPLETE,
        created_at="2026-06-10T00:00:00Z",
        updated_at="2026-06-10T00:00:00Z",
        attempts=[_learning_attempt(str(missing), "relative/review.md")],
    )
    (session_dir / "run-record.json").write_text(json.dumps(record.to_dict()), encoding="utf-8")
    run_store = RunStore(tmp_path / "state")

    run_store.archive(record)

    archive = run_store.archive_dir(record.run_id)
    assert not (archive / "final-diff.patch").exists()
    assert not (archive / "review.md").exists()
    assert not (archive / "pi-session.jsonl").exists()


def test_rebuild_tolerates_missing_sessions_dir(tmp_path):
    index = RunIndex(tmp_path / "runs.db")

    index.rebuild_from_workspace(tmp_path / "missing-repo")

    assert index.get_run("run-1") is None


def test_rebuild_skips_corrupt_record_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RunStore(global_root=tmp_path / "global")
    store.write(repo, make_run())
    corrupt_dir = repo / ".sessions" / "run-corrupt"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "run-record.json").write_text("{not json", encoding="utf-8")
    bad_state_dir = repo / ".sessions" / "run-bad-state"
    bad_state_dir.mkdir(parents=True)
    (bad_state_dir / "run-record.json").write_text(
        json.dumps({**make_run().to_dict(), "run_id": "run-bad-state", "state": "NOPE"}),
        encoding="utf-8",
    )
    index = RunIndex(tmp_path / "runs.db")

    index.rebuild_from_workspace(repo)

    assert index.get_run("run-1") == make_run()
    assert index.get_run("run-corrupt") is None
    assert index.get_run("run-bad-state") is None
