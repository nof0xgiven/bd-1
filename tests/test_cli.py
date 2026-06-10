import json
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

import pytest

from bd1.cli import build_parser, main, read_task_argument
from bd1.config import default_workspace_config, write_workspace_config
from bd1.errors import Bd1Error
from bd1.git import branch_exists
from bd1.models import RunRecord, RunState
from bd1.orchestrator import Orchestrator
from bd1.registry import WorkspaceRegistry
from bd1.run_store import RunStore
from tests.fakes import FakePiRunner, FakePrRunner, FakeReasoning, FakeVetRunner


def test_run_accepts_task_without_workspace():
    args = build_parser().parse_args(["run", "Fix bug"])

    assert args.command == "run"
    assert args.workspace is None
    assert args.task == "Fix bug"


def test_run_accepts_file_without_workspace():
    args = build_parser().parse_args(["run", "--file", "task.md"])

    assert args.command == "run"
    assert args.workspace is None
    assert args.file == "task.md"
    assert args.task is None


def test_workspace_add_parser():
    args = build_parser().parse_args(
        [
            "workspace",
            "add",
            "--name",
            "demo",
            "--repo",
            "/tmp/demo",
            "--product",
            "Demo product",
        ]
    )

    assert args.command == "workspace"
    assert args.workspace_command == "add"
    assert args.name == "demo"


def test_read_task_argument_from_file(tmp_path):
    task_file = tmp_path / "task.md"
    task_file.write_text("Fix the bug\n", encoding="utf-8")

    assert read_task_argument(None, str(task_file)) == "Fix the bug"


def test_main_catches_bd1_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))

    assert main(["workspace", "profile", "missing"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Workspace is not registered: missing" in captured.err


def test_workspace_add_list_and_profile_cli(tmp_path, init_git_repo, monkeypatch, capsys):
    repo = init_git_repo(tmp_path / "repo")
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("BD1_REASONING", "template")

    assert (
        main(
            [
                "workspace",
                "add",
                "--name",
                "demo",
                "--repo",
                str(repo),
                "--product",
                "Demo product",
            ]
        )
        == 0
    )
    add_output = capsys.readouterr()
    assert "Review and commit generated bd-1 workspace files" in add_output.out

    assert main(["workspace", "list"]) == 0
    list_output = capsys.readouterr()
    assert "demo" in list_output.out
    assert str(repo.resolve()) in list_output.out

    assert main(["workspace", "profile", "demo"]) == 0
    profile_output = capsys.readouterr()
    assert "Profile artifacts written for workspace demo" in profile_output.out


def test_workspace_add_default_profile_uses_reasoning(tmp_path, init_git_repo, monkeypatch):
    repo = init_git_repo(tmp_path / "repo")
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("BD1_REASONING", "template")

    args = [
        "workspace",
        "add",
        "--name",
        "demo",
        "--repo",
        str(repo),
        "--product",
        "Demo product",
    ]
    assert main(args) == 0

    product = (repo / ".artifacts" / "product.md").read_text(encoding="utf-8")
    assert "Template profile." in product


def test_workspace_add_profile_keyword_skips_reasoning(tmp_path, init_git_repo, monkeypatch):
    repo = init_git_repo(tmp_path / "repo")
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("BD1_REASONING", "template")

    args = [
        "workspace",
        "add",
        "--name",
        "demo",
        "--repo",
        str(repo),
        "--product",
        "Demo product",
        "--profile",
        "keyword",
    ]
    assert main(args) == 0

    product = (repo / ".artifacts" / "product.md").read_text(encoding="utf-8")
    assert "Template profile." not in product
    assert "Demo product" in product

    # The profile subcommand honors the same escape hatch.
    (repo / ".artifacts" / "product.md").unlink()
    assert main(["workspace", "profile", "demo", "--profile", "keyword"]) == 0
    product = (repo / ".artifacts" / "product.md").read_text(encoding="utf-8")
    assert "Template profile." not in product


class _ExplodingProfiler:
    def profile(self, **kwargs):
        raise RuntimeError("LM down")


def _add_demo_workspace_args(repo):
    return [
        "workspace",
        "add",
        "--name",
        "demo",
        "--repo",
        str(repo),
        "--product",
        "Demo product",
    ]


def test_workspace_add_and_profile_warn_on_stderr_when_profiling_degrades(
    tmp_path, init_git_repo, monkeypatch, capsys
):
    repo = init_git_repo(tmp_path / "repo")
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("bd1.cli._build_reasoning", lambda config: _ExplodingProfiler())

    assert main(_add_demo_workspace_args(repo)) == 0
    captured = capsys.readouterr()
    assert "warning: agentic profiling failed, keyword fallback used" in captured.err
    assert ".artifacts/profile-warning.md" in captured.err
    assert "keyword fallback" in captured.out
    assert (repo / ".artifacts" / "profile-warning.md").exists()

    assert main(["workspace", "profile", "demo"]) == 0
    captured = capsys.readouterr()
    assert "warning: agentic profiling failed, keyword fallback used" in captured.err
    assert "Profile artifacts written for workspace demo" in captured.out


def test_workspace_profiling_falls_back_when_reasoning_cannot_be_built(
    tmp_path, init_git_repo, monkeypatch, capsys
):
    repo = init_git_repo(tmp_path / "repo")
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))

    def _raise(config):
        raise Bd1Error("dspy_model missing")

    monkeypatch.setattr("bd1.cli._build_reasoning", _raise)

    assert main(_add_demo_workspace_args(repo)) == 0
    captured = capsys.readouterr()
    assert "warning: agentic profiling failed, keyword fallback used" in captured.err
    warning = (repo / ".artifacts" / "profile-warning.md").read_text(encoding="utf-8")
    assert "dspy_model missing" in warning
    assert "Demo product" in (repo / ".artifacts" / "product.md").read_text(encoding="utf-8")

    assert main(["workspace", "profile", "demo"]) == 0
    captured = capsys.readouterr()
    assert "warning: agentic profiling failed, keyword fallback used" in captured.err


def test_workspace_add_survives_reasoning_construction_crash(
    tmp_path, init_git_repo, monkeypatch, capsys
):
    repo = init_git_repo(tmp_path / "repo")
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))

    def _crash(config):
        raise RuntimeError("dspy import exploded")

    monkeypatch.setattr("bd1.cli._build_reasoning", _crash)

    assert main(_add_demo_workspace_args(repo)) == 0
    captured = capsys.readouterr()
    assert "warning: agentic profiling failed, keyword fallback used" in captured.err
    assert (repo / ".artifacts" / "profile-warning.md").exists()
    assert (repo / ".artifacts" / "product.md").exists()


def test_doctor_reports_failures_with_nonzero_exit(tmp_path, init_git_repo, monkeypatch, capsys):
    repo = init_git_repo(tmp_path / "repo")
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))
    assert (
        main(
            [
                "workspace",
                "add",
                "--name",
                "demo",
                "--repo",
                str(repo),
                "--product",
                "Demo product",
                "--profile",
                "keyword",
            ]
        )
        == 0
    )
    capsys.readouterr()
    monkeypatch.setattr("bd1.doctor.shutil.which", lambda name: None)

    assert main(["doctor", "--workspace", "demo"]) == 1

    output = capsys.readouterr().out
    assert "FAIL binary:git" in output
    assert "git not found on PATH" in output


class FakeOrchestrator:
    calls: ClassVar[list] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def run(self, config, task):
        self.__class__.calls.append((config, task, self.kwargs))
        return RunRecord(
            run_id="run-1",
            workspace=config.name,
            task=task,
            base_commit="base",
            branch="bd-1/run-1",
            worktree=config.repo_path,
            state=RunState.COMPLETE,
            created_at="2026-06-09T12:00:00Z",
            updated_at="2026-06-09T12:01:00Z",
            final_verdict="PASS",
        )


def test_run_resolves_workspace_from_current_repo_config(
    tmp_path, init_git_repo, monkeypatch, capsys
):
    repo = init_git_repo(tmp_path / "repo")
    config = default_workspace_config("demo", str(repo), "Demo product", "", "main")
    write_workspace_config(repo, config)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("BD1_REASONING", "template")
    monkeypatch.setattr("bd1.cli.Orchestrator", FakeOrchestrator)
    FakeOrchestrator.calls = []

    assert main(["run", "Fix bug"]) == 0

    assert FakeOrchestrator.calls[0][0].name == "demo"
    assert FakeOrchestrator.calls[0][1] == "Fix bug"
    assert "run-1" in capsys.readouterr().out


def test_run_resolves_sole_registered_workspace_outside_repo(tmp_path, init_git_repo, monkeypatch):
    repo = init_git_repo(tmp_path / "repo")
    state = tmp_path / "state"
    WorkspaceRegistry(state).add(default_workspace_config("demo", str(repo), "Demo", "", "main"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BD1_HOME", str(state))
    monkeypatch.setenv("BD1_REASONING", "template")
    monkeypatch.setattr("bd1.cli.Orchestrator", FakeOrchestrator)
    FakeOrchestrator.calls = []

    assert main(["run", "Fix bug"]) == 0

    assert FakeOrchestrator.calls[0][0].name == "demo"


def test_run_requires_workspace_when_multiple_registered(
    tmp_path, init_git_repo, monkeypatch, capsys
):
    repo_a = init_git_repo(tmp_path / "repo-a")
    repo_b = init_git_repo(tmp_path / "repo-b")
    state = tmp_path / "state"
    registry = WorkspaceRegistry(state)
    registry.add(default_workspace_config("a", str(repo_a), "A", "", "main"))
    registry.add(default_workspace_config("b", str(repo_b), "B", "", "main"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BD1_HOME", str(state))

    assert main(["run", "Fix bug"]) == 1

    assert "Use --workspace" in capsys.readouterr().err


def test_status_reads_authoritative_run_and_refreshes_index(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    repo.mkdir()
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="Fix bug",
        base_commit="base",
        branch="bd-1/run-1",
        worktree=str(repo),
        state=RunState.COMPLETE,
        created_at="2026-06-09T12:00:00Z",
        updated_at="2026-06-09T12:01:00Z",
    )
    RunStore(tmp_path / "state").write(repo, record)

    assert main(["status", "run-1"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["run_id"] == "run-1"
    assert data["state"] == "COMPLETE"
    assert (tmp_path / "state" / "runs.db").exists()


def _feedback_args(run_id: str) -> list[str]:
    return [
        "feedback",
        run_id,
        "--outcome",
        "wrong_behavior",
        "--wrong-or-missing",
        "Missed test",
        "--expected",
        "Add test",
    ]


def test_feedback_writes_record_and_updates_authoritative_run(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state"
    monkeypatch.setenv("BD1_HOME", str(state))
    monkeypatch.setenv("BD1_REASONING", "template")
    repo = tmp_path / "repo"
    repo.mkdir()
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="Fix bug",
        base_commit="base",
        branch="bd-1/run-1",
        worktree=str(repo),
        state=RunState.COMPLETE,
        created_at="2026-06-09T12:00:00Z",
        updated_at="2026-06-09T12:01:00Z",
    )
    store = RunStore(state)
    store.write(repo, record)

    assert main(_feedback_args("run-1")) == 0

    updated = store.read_by_id("run-1")
    assert len(updated.feedback_paths) == 1
    assert (repo / ".sessions" / "run-1" / "feedback-001.json").exists()
    assert (repo / ".artifacts" / "learning" / "run-1-feedback.md").exists()
    store_root = state / "learning" / "demo"
    assert (store_root / "learning.jsonl").exists()
    assert list((store_root / "learnings").glob("*.json"))
    output = capsys.readouterr().out
    assert "feedback-001.json" in output
    assert "pending=1" in output


def test_feedback_twice_keeps_both_records_without_duplicate_paths(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("BD1_HOME", str(state))
    monkeypatch.setenv("BD1_REASONING", "template")
    repo = tmp_path / "repo"
    repo.mkdir()
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="Fix bug",
        base_commit="base",
        branch="bd-1/run-1",
        worktree=str(repo),
        state=RunState.COMPLETE,
        created_at="2026-06-09T12:00:00Z",
        updated_at="2026-06-09T12:01:00Z",
    )
    store = RunStore(state)
    store.write(repo, record)

    assert main(_feedback_args("run-1")) == 0
    assert main(_feedback_args("run-1")) == 0

    updated = store.read_by_id("run-1")
    assert (repo / ".sessions" / "run-1" / "feedback-001.json").exists()
    assert (repo / ".sessions" / "run-1" / "feedback-002.json").exists()
    assert len(updated.feedback_paths) == 2
    assert len(set(updated.feedback_paths)) == 2


def test_feedback_survives_cleaned_worktree(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state"
    monkeypatch.setenv("BD1_HOME", str(state))
    monkeypatch.setenv("BD1_REASONING", "template")
    record_dir = tmp_path / "record-dir"
    record_dir.mkdir()
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="Fix bug",
        base_commit="base",
        branch="bd-1/run-1",
        worktree=str(tmp_path / "gone"),
        state=RunState.COMPLETE,
        created_at="2026-06-09T12:00:00Z",
        updated_at="2026-06-09T12:01:00Z",
    )
    store = RunStore(state)
    store.write(record_dir, record)
    store.archive(record)

    assert main(_feedback_args("run-1")) == 0

    archive_dir = state / "runs" / "run-1"
    assert (archive_dir / "feedback-001.json").exists()
    updated = store.read_by_id("run-1")
    assert updated.feedback_paths == [str(archive_dir / "feedback-001.json")]
    store_root = state / "learning" / "demo"
    assert list((store_root / "learnings").glob("*.json"))
    assert not (tmp_path / "gone").exists()
    output = capsys.readouterr().out
    assert "feedback-001.json" in output


def test_read_task_argument_missing_file_raises_friendly_error(tmp_path):
    with pytest.raises(Bd1Error) as exc:
        read_task_argument(None, str(tmp_path / "missing.md"))

    assert "Unable to read task file" in str(exc.value)


class FakeBlockedOrchestrator(FakeOrchestrator):
    def run(self, config, task):
        record = super().run(config, task)
        self.__class__.calls[-1] = (config, task, self.kwargs)
        return replace(record, state=RunState.BLOCKED, final_verdict="BLOCKED")


def test_run_returns_exit_code_2_when_run_is_blocked(tmp_path, init_git_repo, monkeypatch, capsys):
    repo = init_git_repo(tmp_path / "repo")
    config = default_workspace_config("demo", str(repo), "Demo product", "", "main")
    write_workspace_config(repo, config)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("BD1_REASONING", "template")
    monkeypatch.setattr("bd1.cli.Orchestrator", FakeBlockedOrchestrator)
    FakeBlockedOrchestrator.calls = []

    assert main(["run", "Fix bug"]) == 2

    assert json.loads(capsys.readouterr().out)["state"] == "BLOCKED"


def test_status_unknown_run_id_prints_friendly_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))

    assert main(["status", "run-missing"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Unknown run id: run-missing" in captured.err


def test_clean_archives_run_and_removes_worktree_and_branch(
    tmp_path, init_git_repo, monkeypatch, capsys
):
    state = tmp_path / "state"
    monkeypatch.setenv("BD1_HOME", str(state))
    repo = init_git_repo(tmp_path / "repo")
    config = default_workspace_config("demo", str(repo), "Demo product", "", "main")
    WorkspaceRegistry(state).add(config)
    orchestrator = Orchestrator(
        global_root=state,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
        pr_runner=FakePrRunner(),
    )
    record = orchestrator.run(config, "Fix bug")
    assert record.state is RunState.COMPLETE
    worktree = Path(record.worktree)

    assert main(["clean", record.run_id]) == 0

    clean_output = json.loads(capsys.readouterr().out)
    assert clean_output["worktree_removed"] is True
    assert clean_output["branch_deleted"] is True
    assert not worktree.exists()
    assert not branch_exists(repo, record.branch)
    archive_dir = state / "runs" / record.run_id
    assert (archive_dir / "run-record.json").exists()
    assert (archive_dir / "transitions.jsonl").exists()

    assert main(["status", record.run_id]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["run_id"] == record.run_id
    assert status["state"] == "COMPLETE"


def test_clean_rejects_non_terminal_run(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state"
    monkeypatch.setenv("BD1_HOME", str(state))
    repo = tmp_path / "repo"
    repo.mkdir()
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="Fix bug",
        base_commit="base",
        branch="bd-1/run-1",
        worktree=str(repo),
        state=RunState.EXECUTION_RUNNING,
        created_at="2026-06-09T12:00:00Z",
        updated_at="2026-06-09T12:01:00Z",
    )
    RunStore(state).write(repo, record)

    assert main(["clean", "run-1"]) == 1

    assert "only COMPLETE or BLOCKED" in capsys.readouterr().err


def test_clean_handles_already_missing_worktree(tmp_path, init_git_repo, monkeypatch, capsys):
    state = tmp_path / "state"
    monkeypatch.setenv("BD1_HOME", str(state))
    repo = init_git_repo(tmp_path / "repo")
    WorkspaceRegistry(state).add(default_workspace_config("demo", str(repo), "Demo", "", "main"))
    record_dir = tmp_path / "record-dir"
    record_dir.mkdir()
    record = RunRecord(
        run_id="run-1",
        workspace="demo",
        task="Fix bug",
        base_commit="base",
        branch="bd-1/run-1",
        worktree=str(tmp_path / "gone"),
        state=RunState.BLOCKED,
        created_at="2026-06-09T12:00:00Z",
        updated_at="2026-06-09T12:01:00Z",
        final_verdict="BLOCKED",
    )
    RunStore(state).write(record_dir, record)

    assert main(["clean", "run-1"]) == 0

    clean_output = json.loads(capsys.readouterr().out)
    assert clean_output["worktree_removed"] is False
    assert clean_output["branch_deleted"] is False
    assert (state / "runs" / "run-1" / "run-record.json").exists()
