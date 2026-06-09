from bd1.subprocesses import CommandResult, run_command


def test_run_command_captures_output(tmp_path):
    result = run_command(["python", "-c", "print('hello')"], cwd=tmp_path)

    assert result == CommandResult(
        exit_code=0,
        stdout="hello\n",
        stderr="",
        command=["python", "-c", "print('hello')"],
    )
