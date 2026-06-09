from bd1.cli import build_parser, main, read_task_argument


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
