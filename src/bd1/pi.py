from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bd1.artifacts import write_text
from bd1.subprocesses import CommandResult, run_command

CommandRunner = Callable[..., CommandResult]


@dataclass(frozen=True)
class PiResult:
    command: list[str]
    exit_code: int
    stdout_path: Path
    stderr_path: Path
    session_file: Path | None
    session_id: str
    error: str = ""


class PiRunner:
    def __init__(
        self,
        *,
        pi_command: str = "pi",
        pi_model: str = "",
        pi_provider: str = "",
        command_runner: CommandRunner = run_command,
    ) -> None:
        self.pi_command = pi_command
        self.pi_model = pi_model
        self.pi_provider = pi_provider
        self._run_command = command_runner

    def run(
        self,
        *,
        worktree: str | Path,
        prompt: str,
        session_id: str,
        session_dir: str | Path,
        artifact_dir: str | Path,
    ) -> PiResult:
        session_path = Path(session_dir)
        command = [
            self.pi_command,
            "-p",
            prompt,
            "--session-id",
            session_id,
            "--session-dir",
            str(session_path),
        ]
        if self.pi_model:
            command.extend(["--model", self.pi_model])
        if self.pi_provider:
            command.extend(["--provider", self.pi_provider])

        result = self._run_command(command, cwd=worktree)
        artifact_path = Path(artifact_dir)
        stdout_path = write_text(artifact_path / "pi-stdout.txt", result.stdout, redact=True)
        stderr_path = write_text(artifact_path / "pi-stderr.txt", result.stderr, redact=True)

        session_file = _latest_session_file(session_path)
        if session_file is None:
            error = f"No Pi session JSONL found under {session_path}"
            exit_code = result.exit_code if result.exit_code != 0 else 2
            return PiResult(
                command=list(command),
                exit_code=exit_code,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                session_file=None,
                session_id=session_id,
                error=error,
            )

        return PiResult(
            command=list(command),
            exit_code=result.exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            session_file=session_file,
            session_id=session_id,
        )


def _latest_session_file(session_dir: Path) -> Path | None:
    if not session_dir.exists():
        return None
    files = sorted(
        (path for path in session_dir.rglob("*.jsonl") if path.is_file()),
        key=lambda path: (path.stat().st_mtime_ns, path.as_posix()),
        reverse=True,
    )
    return files[0] if files else None
