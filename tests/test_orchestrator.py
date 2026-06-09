import json
from pathlib import Path

import pytest

from bd1.config import default_workspace_config
from bd1.errors import DirtyRepositoryError
from bd1.git import get_status_porcelain
from bd1.models import RunState
from bd1.orchestrator import Orchestrator, compile_execution_prompt
from bd1.run_index import RunIndex
from tests.fakes import FakePiBehavior, FakePiRunner, FakeReasoning, FakeSetupRunner, FakeVetRunner


def make_config(repo: Path, *, max_attempts: int = 5, setup_script: str = ""):
    config = default_workspace_config("demo", str(repo), "Demo product", setup_script, "main")
    return config.__class__.from_dict({**config.to_dict(), "max_attempts": max_attempts})


def make_orchestrator(tmp_path, **overrides) -> Orchestrator:
    overrides.setdefault("reasoning", FakeReasoning(["PASS"]))
    return Orchestrator(global_root=tmp_path / "global", **overrides)


def test_dirty_base_fails_before_worktree_creation(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    orchestrator = make_orchestrator(tmp_path)

    with pytest.raises(DirtyRepositoryError):
        orchestrator.run(make_config(repo), "Fix bug")

    assert not (tmp_path / "global" / "worktrees").exists()


def test_setup_failure_blocks_and_writes_setup_artifacts(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(tmp_path, setup_runner=FakeSetupRunner(exit_code=7))

    record = orchestrator.run(make_config(repo, setup_script="setup"), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert record.blocker_path
    assert (Path(record.worktree) / ".sessions" / record.run_id / "setup-stderr.txt").exists()


def test_execution_prompt_contains_executor_contract_clauses():
    prompt = compile_execution_prompt(
        task="Fix bug",
        discovery_context_path=".artifacts/context/fix.md",
        plan_path=".artifacts/plans/fix.md",
        workspace_root="/repo",
        worktree_root="/worktree",
        completion_summary_path=".artifacts/completed/fix.md",
    )

    for clause in [
        "Read `.artifacts/` documentation",
        "Work only in the task worktree",
        "write the smallest failing real test first",
        "Modify only files required",
        "Run focused tests and required quality gates",
        "Commit changes before exit",
        "Resolve pre-commit failures without workarounds or hacks",
        "Leave the worktree clean before exit",
        ".artifacts/completed/fix.md",
    ]:
        assert clause in prompt


def test_happy_path_persists_transitions_and_is_indexable(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    transitions = (
        Path(record.worktree) / ".sessions" / record.run_id / "transitions.jsonl"
    ).read_text(encoding="utf-8")
    for state in [
        "BASE_VERIFIED",
        "WORKTREE_CREATED",
        "DISCOVERY_COMPLETE",
        "PLAN_COMPLETE",
        "EXECUTION_PROMPT_READY",
        "EXECUTION_RUNNING",
        "EXECUTION_COMMITTED",
        "VET_PASSED",
        "REVIEW_PASSED",
        "COMPLETE",
    ]:
        assert state in transitions

    index = RunIndex(tmp_path / "runs.db")
    index.rebuild_from_workspace(Path(record.worktree))
    assert index.get_run(record.run_id) == record


def test_complete_run_leaves_task_worktree_clean_after_learning_capture(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")
    worktree = Path(record.worktree)

    assert record.state is RunState.COMPLETE
    assert (worktree / ".examples" / "learning.jsonl").exists()
    assert get_status_porcelain(worktree) == []

    source_example = repo / ".examples" / "learning.jsonl"
    source_example.parent.mkdir()
    source_example.write_text('{"event":"source"}\n', encoding="utf-8")
    assert "?? .examples/" in get_status_porcelain(repo)


def test_dirty_worktree_resumes_same_session_with_exact_prompt(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    pi = FakePiRunner(
        [
            FakePiBehavior(create_session=True, commit=False, dirty=True),
            FakePiBehavior(create_session=True, commit=True, dirty=False),
        ]
    )
    orchestrator = make_orchestrator(tmp_path, pi_runner=pi, vet_runner=FakeVetRunner([0]))

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    assert pi.prompts[1] == "commit and resolve before exit"
    assert pi.session_ids[0] == pi.session_ids[1]


def test_missing_pi_session_blocks_before_vet(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    vet = FakeVetRunner([0])
    orchestrator = make_orchestrator(
        tmp_path,
        pi_runner=FakePiRunner([FakePiBehavior(create_session=False, commit=True)]),
        vet_runner=vet,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert vet.calls == 0
    assert "No Pi session JSONL" in Path(record.blocker_path).read_text(encoding="utf-8")


def test_vet_findings_loop_review_failure_loop_and_learning_events(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    reasoning = FakeReasoning(["FAIL", "PASS"])
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=reasoning,
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([10, 0, 0]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    assert len(record.attempts) == 3
    assert any("vet findings" in event for event in reasoning.learn_events)
    assert any("review failed" in event for event in reasoning.learn_events)
    assert any("pass" in event for event in reasoning.learn_events)


@pytest.mark.parametrize("exit_code", [1, 2])
def test_vet_runtime_and_config_errors_block(tmp_path, init_git_repo, exit_code):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([exit_code]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert "Vet failed" in Path(record.blocker_path).read_text(encoding="utf-8")


def test_repeated_vet_findings_max_attempts_writes_blocker(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([10, 10, 10]),
    )

    record = orchestrator.run(make_config(repo, max_attempts=2), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert "Max attempts reached" in Path(record.blocker_path).read_text(encoding="utf-8")
    assert json.loads(
        (Path(record.worktree) / ".sessions" / record.run_id / "run-record.json").read_text()
    )
