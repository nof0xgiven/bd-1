import sys

from bd1.subprocesses import CommandResult, run_command


def test_run_command_captures_output(tmp_path):
    result = run_command([sys.executable, "-c", "print('hello')"], cwd=tmp_path)

    assert result == CommandResult(
        exit_code=0,
        stdout="hello\n",
        stderr="",
        command=[sys.executable, "-c", "print('hello')"],
    )


def test_run_command_timeout_returns_controlled_result(tmp_path):
    result = run_command(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        cwd=tmp_path,
        timeout=0.01,
    )

    assert result.exit_code == 124
    assert result.command == [sys.executable, "-c", "import time; time.sleep(2)"]
    assert "timed out" in result.stderr
