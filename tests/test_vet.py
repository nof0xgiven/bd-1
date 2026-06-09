import json
from pathlib import Path

import pytest

from bd1.subprocesses import CommandResult
from bd1.vet import VetRunner


def fake_vet_runner(exit_code: int, output_payload: object | None = None):
    def runner(command, cwd, env=None, timeout=None):
        output_path = Path(command[command.index("--output") + 1])
        if output_payload is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(output_payload), encoding="utf-8")
        return CommandResult(
            exit_code=exit_code,
            stdout=f"stdout-{exit_code}",
            stderr=f"stderr-{exit_code}",
            command=list(command),
        )

    return runner


@pytest.mark.parametrize(
    ("exit_code", "expected_outcome"),
    [(0, "PASS"), (10, "FINDINGS"), (1, "RUNTIME_ERROR"), (2, "CONFIG_ERROR")],
)
def test_vet_runner_preserves_exit_codes_and_artifacts(tmp_path, exit_code, expected_outcome):
    payload = (
        {"issues": [{"code": "goal_mismatch", "message": "Wrong goal"}]}
        if exit_code == 10
        else {"issues": []}
    )
    runner = VetRunner(command_runner=fake_vet_runner(exit_code, payload))

    result = runner.run(
        repo_path=tmp_path,
        task="Fix bug",
        base_commit="HEAD",
        model="flash",
        history_loader_command="bd1-pi-history-loader session.jsonl",
        artifact_dir=tmp_path / ".sessions" / "run-1" / "attempt-1",
    )

    assert result.exit_code == exit_code
    assert result.outcome == expected_outcome
    assert result.stdout_path.read_text(encoding="utf-8") == f"stdout-{exit_code}"
    assert result.stderr_path.read_text(encoding="utf-8") == f"stderr-{exit_code}"
    assert "--history-loader" in result.command
    if exit_code == 10:
        assert "goal_mismatch" in result.findings_summary
        assert "Wrong goal" in result.findings_summary


def test_vet_runner_summarizes_stderr_when_json_absent(tmp_path):
    runner = VetRunner(command_runner=fake_vet_runner(2, None))

    result = runner.run(
        repo_path=tmp_path,
        task="Fix bug",
        base_commit="HEAD",
        model="flash",
        history_loader_command="bd1-pi-history-loader session.jsonl",
        artifact_dir=tmp_path / ".sessions" / "run-1" / "attempt-1",
    )

    assert result.exit_code == 2
    assert result.findings_summary == "stderr-2"
