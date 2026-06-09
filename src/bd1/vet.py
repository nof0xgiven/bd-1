from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bd1.artifacts import write_text
from bd1.subprocesses import CommandResult, run_command

CommandRunner = Callable[..., CommandResult]


@dataclass(frozen=True)
class VetResult:
    command: list[str]
    exit_code: int
    outcome: str
    stdout_path: Path
    stderr_path: Path
    output_path: Path
    findings_summary: str


class VetRunner:
    def __init__(
        self,
        *,
        vet_command: str = "vet",
        command_runner: CommandRunner = run_command,
    ) -> None:
        self.vet_command = vet_command
        self._run_command = command_runner

    def run(
        self,
        *,
        repo_path: str | Path,
        task: str,
        base_commit: str,
        model: str,
        history_loader_command: str,
        artifact_dir: str | Path,
        confidence_threshold: float | None = None,
    ) -> VetResult:
        artifact_path = Path(artifact_dir)
        output_path = artifact_path / "vet-output.json"
        command = [
            self.vet_command,
            task,
            "--repo",
            str(Path(repo_path)),
            "--base-commit",
            base_commit,
            "--model",
            model,
            "--history-loader",
            history_loader_command,
            "--output-format",
            "json",
            "--output",
            str(output_path),
        ]
        if confidence_threshold is not None:
            command.extend(["--confidence-threshold", str(confidence_threshold)])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = self._run_command(command, cwd=repo_path)
        stdout_path = write_text(artifact_path / "vet-stdout.txt", result.stdout, redact=True)
        stderr_path = write_text(artifact_path / "vet-stderr.txt", result.stderr, redact=True)

        return VetResult(
            command=list(command),
            exit_code=result.exit_code,
            outcome=_outcome_for_exit_code(result.exit_code),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            output_path=output_path,
            findings_summary=_findings_summary(output_path, result.stderr),
        )


def _outcome_for_exit_code(exit_code: int) -> str:
    if exit_code == 0:
        return "PASS"
    if exit_code == 10:
        return "FINDINGS"
    if exit_code == 1:
        return "RUNTIME_ERROR"
    if exit_code == 2:
        return "CONFIG_ERROR"
    return "ERROR"


def _findings_summary(output_path: Path, stderr: str) -> str:
    if output_path.exists() and output_path.read_text(encoding="utf-8").strip():
        try:
            data = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return stderr.strip()
        summary = _summarize_json(data)
        if summary:
            return summary
    return stderr.strip()


def _summarize_json(data: Any) -> str:
    findings = _extract_findings(data)
    if not findings:
        return ""
    lines = []
    for finding in findings:
        if isinstance(finding, dict):
            code = finding.get("code") or finding.get("issue_code") or finding.get("id") or "issue"
            message = (
                finding.get("message") or finding.get("description") or finding.get("summary") or ""
            )
            lines.append(f"{code}: {message}".strip())
        else:
            lines.append(str(finding))
    return "\n".join(lines)


def _extract_findings(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("issues", "findings", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []
