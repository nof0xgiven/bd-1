from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from bd1.artifacts import write_text
from bd1.dspy_programs import DiscoveryOutput, LearningOutput, PlanOutput, ReviewOutput
from bd1.pi import PiResult
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
        stderr_path = write_text(artifact_path / "pi-stderr.txt", "")
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
            exit_code=0,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            session_file=session_file,
            session_id=session_id,
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
