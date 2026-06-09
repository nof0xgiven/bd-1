from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from bd1.artifacts import write_text
from bd1.dspy_programs import DiscoveryOutput, LearningOutput, PlanOutput, ReviewOutput
from bd1.pi import PiResult
from bd1.pr import PrCheck, PrPublication, PrResult
from bd1.subprocesses import CommandResult
from bd1.vet import VetResult


class FakeReasoning:
    def __init__(self, review_verdicts: list[str] | None = None) -> None:
        self.review_verdicts = review_verdicts or ["PASS"]
        self.review_calls = 0
        self.learn_events: list[str] = []

    def discover(self, evidence) -> DiscoveryOutput:
        return DiscoveryOutput(markdown=f"# Discovery\n\nTask: {evidence.task}\n")

    def plan(self, evidence, *, discovery_context: str) -> PlanOutput:
        return PlanOutput(markdown=f"# Plan\n\n{discovery_context}\n")

    def review(
        self,
        *,
        task: str,
        discovery_context: str,
        implementation_plan: str,
        pi_completion_summary: str,
        command_output_summary: str,
        git_diff: str,
        vet_json: str,
        workspace_artifacts: str,
    ) -> ReviewOutput:
        verdict = self.review_verdicts[min(self.review_calls, len(self.review_verdicts) - 1)]
        self.review_calls += 1
        return ReviewOutput(verdict=verdict, markdown=f"# Review\n\nVerdict: {verdict}\n")

    def learn(
        self,
        evidence,
        *,
        review_markdown: str,
        final_diff: str = "",
        pr_feedback: str = "",
    ) -> LearningOutput:
        self.learn_events.append(review_markdown)
        return LearningOutput(markdown=f"# Learning\n\n{review_markdown}\n")


@dataclass
class FakePiBehavior:
    create_session: bool = True
    commit: bool = True
    dirty: bool = False
    exit_code: int = 0
    stderr: str = ""
    error: str = ""


class FakePiRunner:
    def __init__(self, behaviors: list[FakePiBehavior] | None = None) -> None:
        self.behaviors = behaviors or [FakePiBehavior()]
        self.prompts: list[str] = []
        self.session_ids: list[str] = []

    def run(
        self,
        *,
        worktree,
        prompt: str,
        session_id: str,
        session_dir,
        artifact_dir,
    ) -> PiResult:
        index = len(self.prompts)
        behavior = self.behaviors[min(index, len(self.behaviors) - 1)]
        self.prompts.append(prompt)
        self.session_ids.append(session_id)

        worktree_path = Path(worktree)
        session_dir_path = Path(session_dir)
        artifact_path = Path(artifact_dir)
        stdout_path = write_text(artifact_path / "pi-stdout.txt", f"pi call {index}\n")
        stderr_path = write_text(artifact_path / "pi-stderr.txt", behavior.stderr)
        session_file = None
        if behavior.create_session:
            session_dir_path.mkdir(parents=True, exist_ok=True)
            session_file = session_dir_path / f"session-{index}.jsonl"
            session_file.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "session", "id": session_id}),
                        json.dumps(
                            {
                                "type": "message",
                                "id": f"m-{index}",
                                "message": {
                                    "role": "assistant",
                                    "content": [{"type": "text", "text": f"done {index}"}],
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

        changed = worktree_path / "change.txt"
        with changed.open("a", encoding="utf-8") as handle:
            handle.write(f"{prompt}\n")
        if behavior.commit:
            subprocess.run(["git", "add", "-A"], cwd=worktree_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"fake pi {index}"],
                cwd=worktree_path,
                check=True,
                capture_output=True,
                text=True,
            )
        if behavior.dirty:
            (worktree_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        return PiResult(
            command=["fake-pi"],
            exit_code=behavior.exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            session_file=session_file,
            session_id=session_id,
            error=behavior.error,
        )


class FakeSetupRunner:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code

    def run(self, worktree, setup_script: str, artifact_dir) -> CommandResult:
        artifact_path = Path(artifact_dir)
        write_text(artifact_path / "setup-stdout.txt", "setup stdout")
        write_text(artifact_path / "setup-stderr.txt", "setup stderr")
        return CommandResult(self.exit_code, "setup stdout", "setup stderr", ["setup"])


class FakeVetRunner:
    def __init__(self, exit_codes: list[int] | None = None) -> None:
        self.exit_codes = exit_codes or [0]
        self.calls = 0

    def run(
        self,
        *,
        repo_path,
        task: str,
        base_commit: str,
        model: str,
        history_loader_command: str,
        artifact_dir,
        confidence_threshold: float | None = None,
    ) -> VetResult:
        exit_code = self.exit_codes[min(self.calls, len(self.exit_codes) - 1)]
        self.calls += 1
        artifact_path = Path(artifact_dir)
        output_path = artifact_path / "vet-output.json"
        payload = (
            {"issues": [{"issue_code": "goal_mismatch", "description": "Wrong goal"}]}
            if exit_code == 10
            else {"issues": []}
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        stdout_path = write_text(artifact_path / "vet-stdout.txt", "vet stdout")
        stderr_path = write_text(artifact_path / "vet-stderr.txt", "vet stderr")
        outcome = {0: "PASS", 10: "FINDINGS", 1: "RUNTIME_ERROR", 2: "CONFIG_ERROR"}.get(
            exit_code, "ERROR"
        )
        summary = "goal_mismatch: Wrong goal" if exit_code == 10 else "vet stderr"
        return VetResult(
            command=["fake-vet"],
            exit_code=exit_code,
            outcome=outcome,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            output_path=output_path,
            findings_summary=summary,
        )


class FakePrRunner:
    def __init__(
        self,
        results: list[PrResult] | None = None,
        *,
        publish_error: Exception | None = None,
        monitor_error: Exception | None = None,
    ) -> None:
        self.results = results or [
            PrResult(
                number=1,
                url="https://github.com/acme/demo/pull/1",
                state="OPEN",
                checks=[PrCheck("tests", "pass", "SUCCESS", "", "")],
                feedback=[],
                merge_conflict=False,
                complete_artifact_path=".artifacts/pr/fix-bug-1-complete.md",
            )
        ]
        self.publish_error = publish_error
        self.monitor_error = monitor_error
        self.publish_calls = []
        self.monitor_calls = []

    def publish_or_update(self, **kwargs) -> PrPublication:
        self.publish_calls.append(kwargs)
        if self.publish_error:
            raise self.publish_error
        result = self.results[min(len(self.publish_calls) - 1, len(self.results) - 1)]
        return PrPublication(number=result.number, url=result.url, state=result.state)

    def monitor(self, **kwargs) -> PrResult:
        self.monitor_calls.append(kwargs)
        if self.monitor_error:
            raise self.monitor_error
        result = self.results[min(len(self.monitor_calls) - 1, len(self.results) - 1)]
        worktree = Path(kwargs["worktree"])
        artifact_path = result.artifact_path
        complete_artifact_path = result.complete_artifact_path
        if result.artifact_path:
            path = worktree / result.artifact_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "# PR Feedback\n\n## Consolidated Resolve Prompt\n\nResolve PR feedback.\n",
                encoding="utf-8",
            )
            artifact_path = str(path)
        if result.complete_artifact_path:
            path = worktree / result.complete_artifact_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# PR Feedback Complete\n", encoding="utf-8")
            complete_artifact_path = str(path)
        return replace(
            result,
            artifact_path=artifact_path,
            complete_artifact_path=complete_artifact_path,
        )
