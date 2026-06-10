from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bd1.artifacts import write_text
from bd1.subprocesses import CommandResult, run_command

CommandRunner = Callable[..., CommandResult]


class SetupRunner:
    def __init__(self, command_runner: CommandRunner = run_command) -> None:
        self._run_command = command_runner

    def run(
        self,
        worktree: str | Path,
        setup_script: str,
        artifact_dir: str | Path,
    ) -> CommandResult:
        artifact_path = Path(artifact_dir)
        if not setup_script.strip():
            result = CommandResult(0, "", "", [])
        else:
            result = self._run_command(["sh", "-c", setup_script], cwd=worktree)

        write_text(artifact_path / "setup-stdout.txt", result.stdout, redact=True)
        write_text(artifact_path / "setup-stderr.txt", result.stderr, redact=True)
        return result
