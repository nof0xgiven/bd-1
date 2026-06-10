import sys

import pytest

from bd1.errors import CommandStartError
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


def test_run_command_missing_binary_raises_bd1_error(tmp_path):
    with pytest.raises(CommandStartError) as exc:
        run_command(["bd1-definitely-missing-binary"], cwd=tmp_path)

    assert "bd1-definitely-missing-binary" in str(exc.value)


def test_run_command_gives_children_no_stdin(tmp_path):
    result = run_command(
        [sys.executable, "-c", "import sys; print(len(sys.stdin.read()))"],
        cwd=tmp_path,
        timeout=10,
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "0"


def test_run_command_replaces_undecodable_output(tmp_path):
    result = run_command(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'ok\\xff')",
        ],
        cwd=tmp_path,
    )

    assert result.exit_code == 0
    assert result.stdout == "ok�"
