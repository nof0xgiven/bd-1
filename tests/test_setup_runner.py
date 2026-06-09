from bd1.setup_runner import SetupRunner


def test_setup_runner_runs_script_and_writes_artifacts(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    artifact_dir = worktree / ".sessions" / "run-1"

    result = SetupRunner().run(
        worktree,
        "printf setup-out && printf setup-err >&2",
        artifact_dir,
    )

    assert result.exit_code == 0
    assert (artifact_dir / "setup-stdout.txt").read_text(encoding="utf-8") == "setup-out"
    assert (artifact_dir / "setup-stderr.txt").read_text(encoding="utf-8") == "setup-err"


def test_setup_runner_preserves_nonzero_exit(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    artifact_dir = worktree / ".sessions" / "run-1"

    result = SetupRunner().run(worktree, "printf bad >&2; exit 7", artifact_dir)

    assert result.exit_code == 7
    assert (artifact_dir / "setup-stderr.txt").read_text(encoding="utf-8") == "bad"
