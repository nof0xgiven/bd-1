import json
from typing import ClassVar

from bd1.cli import build_parser, main, read_task_argument
from bd1.config import default_workspace_config, write_workspace_config
from bd1.models import RunRecord, RunState
from bd1.registry import WorkspaceRegistry
from bd1.run_store import RunStore


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


def test_feedback_writes_record_and_updates_authoritative_run(tmp_path, monkeypatch):
    monkeypatch.setenv("BD1_HOME", str(tmp_path / "state"))
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
    store = RunStore(tmp_path / "state")
    store.write(repo, record)

    assert (
        main(
            [
                "feedback",
                "run-1",
                "--outcome",
                "wrong_behavior",
                "--wrong-or-missing",
                "Missed test",
                "--expected",
                "Add test",
            ]
        )
        == 0
    )

    updated = store.read_by_id("run-1")
    assert len(updated.feedback_paths) == 1
    assert (repo / ".sessions" / "run-1" / "feedback.json").exists()
    assert (repo / ".artifacts" / "learning" / "run-1-feedback.md").exists()
