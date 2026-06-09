from dataclasses import replace

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
