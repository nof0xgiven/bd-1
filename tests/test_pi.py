from pathlib import Path

from bd1.pi import PiRunner
from bd1.subprocesses import CommandResult


def fake_pi_runner(*, writes_session: bool = True, exit_code: int = 0):
    def runner(command, cwd, env=None, timeout=None):
        assert "--session-dir" in command, f"--session-dir missing from pi command: {command}"
        session_dir = Path(command[command.index("--session-dir") + 1])
        if writes_session:
            session_dir.mkdir(parents=True, exist_ok=True)
            (session_dir / "session.jsonl").write_text(
                '{"type":"session","id":"session-1"}\n',
                encoding="utf-8",
            )
        return CommandResult(exit_code, "pi stdout", "pi stderr", list(command))

    return runner


def test_pi_runner_builds_command_and_returns_session_file(tmp_path):
    runner = PiRunner(
        pi_command="pi",
        pi_model="gpt-5",
        pi_provider="openai",
        command_runner=fake_pi_runner(),
    )
    artifact_dir = tmp_path / ".sessions" / "run-1" / "attempt-1"

    result = runner.run(
        worktree=tmp_path,
        prompt="Fix bug",
        session_id="session-1",
        session_dir=tmp_path / "pi-sessions",
        artifact_dir=artifact_dir,
    )

    assert result.exit_code == 0
    assert result.session_file == tmp_path / "pi-sessions" / "session.jsonl"
    assert result.command == [
        "pi",
        "-p",
        "Fix bug",
        "--session-id",
        "session-1",
        "--session-dir",
        str(tmp_path / "pi-sessions"),
        "--model",
        "gpt-5",
        "--provider",
        "openai",
    ]
    assert result.stdout_path.read_text(encoding="utf-8") == "pi stdout"
    assert result.stderr_path.read_text(encoding="utf-8") == "pi stderr"


def test_pi_runner_does_not_fabricate_missing_session(tmp_path):
    runner = PiRunner(command_runner=fake_pi_runner(writes_session=False))

    result = runner.run(
        worktree=tmp_path,
        prompt="Fix bug",
        session_id="session-1",
        session_dir=tmp_path / "pi-sessions",
        artifact_dir=tmp_path / ".sessions" / "run-1" / "attempt-1",
    )

    assert result.exit_code == 2
    assert result.session_file is None
    assert "No Pi session JSONL" in result.error
