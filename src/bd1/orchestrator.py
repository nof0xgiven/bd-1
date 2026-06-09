from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from bd1.artifacts import ensure_workspace_dirs, write_text
from bd1.dspy_programs import DspyReasoningPrograms, ReasoningPrograms
from bd1.evidence import EvidencePackage, collect_evidence
from bd1.git import (
    create_worktree,
    diff_from_base,
    ensure_clean_repo,
    ensure_git_repo,
    get_head_commit,
    get_status_porcelain,
    git,
)
from bd1.learning import ExampleStore
from bd1.models import AttemptRecord, RunRecord, RunState, WorkspaceConfig
from bd1.paths import global_state_dir, make_run_id, slugify
from bd1.pi import PiResult, PiRunner
from bd1.run_store import RunStore, now_iso
from bd1.setup_runner import SetupRunner
from bd1.vet import VetResult, VetRunner

RUNTIME_EXCLUDES = (
    ".sessions/",
    ".artifacts/context/",
    ".artifacts/plans/",
    ".artifacts/vet/",
    ".artifacts/reviews/",
    ".artifacts/blockers/",
    ".artifacts/completed/",
    ".artifacts/learning/",
    "*.db",
    "*.sqlite",
)


def compile_execution_prompt(
    *,
    task: str,
    discovery_context_path: str,
    plan_path: str,
    workspace_root: str,
    worktree_root: str,
    completion_summary_path: str,
) -> str:
    return "\n\n".join(
        [
            "# Executor Contract",
            f"Task: {task}",
            f"Workspace root: {workspace_root}",
            f"Task worktree: {worktree_root}",
            f"Discovery context path: {discovery_context_path}",
            f"Implementation plan path: {plan_path}",
            "Read `.artifacts/` documentation before editing.",
            "Work only in the task worktree.",
            "For meaningful behavior changes, write the smallest failing real test first.",
            "Modify only files required by the task and plan.",
            "Run focused tests and required quality gates.",
            "Commit changes before exit.",
            "Resolve pre-commit failures without workarounds or hacks.",
            "Leave the worktree clean before exit.",
            f"Write completion summary to {completion_summary_path}.",
        ]
    )


class Orchestrator:
    def __init__(
        self,
        *,
        global_root: str | Path | None = None,
        reasoning: ReasoningPrograms | None = None,
        setup_runner: SetupRunner | None = None,
        pi_runner: PiRunner | None = None,
        vet_runner: VetRunner | None = None,
        run_store: RunStore | None = None,
    ) -> None:
        self.global_root = Path(global_root) if global_root else global_state_dir()
        self.reasoning = reasoning or DspyReasoningPrograms()
        self.setup_runner = setup_runner or SetupRunner()
        self.pi_runner = pi_runner or PiRunner()
        self.vet_runner = vet_runner or VetRunner()
        self.run_store = run_store or RunStore(self.global_root)

    def run(self, config: WorkspaceConfig, task: str) -> RunRecord:
        repo = Path(config.repo_path).expanduser().resolve()
        ensure_git_repo(repo)
        ensure_clean_repo(repo)
        base_commit = get_head_commit(repo)

        run_id = make_run_id(task)
        branch = f"bd-1/{run_id}"
        worktree = self.global_root / "worktrees" / config.name / run_id
        create_worktree(repo, worktree, branch, base_commit)
        _ignore_runtime_paths(worktree)
        ensure_workspace_dirs(worktree)

        record = RunRecord(
            run_id=run_id,
            workspace=config.name,
            task=task,
            base_commit=base_commit,
            branch=branch,
            worktree=str(worktree),
            state=RunState.TASK_RECEIVED,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        self.run_store.write(worktree, record)
        record = self._transition(worktree, record, RunState.BASE_VERIFIED, "base clean")
        record = self._transition(worktree, record, RunState.WORKTREE_CREATED, "worktree created")

        run_dir = worktree / ".sessions" / run_id
        if config.setup_script:
            setup_result = self.setup_runner.run(worktree, config.setup_script, run_dir)
            if setup_result.exit_code != 0:
                evidence = collect_evidence(worktree, task=task)
                return self._block(
                    worktree,
                    record,
                    "Setup failed",
                    f"Setup script exited {setup_result.exit_code}.",
                    evidence,
                )

        evidence = collect_evidence(worktree, task=task)
        task_slug = slugify(task)
        discovery_path = worktree / ".artifacts" / "context" / f"{task_slug}.md"
        plan_path = worktree / ".artifacts" / "plans" / f"{task_slug}.md"
        completed_path = worktree / ".artifacts" / "completed" / f"{task_slug}.md"

        discovery = self.reasoning.discover(evidence)
        write_text(discovery_path, discovery.markdown, redact=True)
        record = replace(
            record,
            artifacts={**record.artifacts, "discovery_context": str(discovery_path)},
        )
        self.run_store.write(worktree, record)
        record = self._transition(
            worktree, record, RunState.DISCOVERY_COMPLETE, "discovery complete"
        )

        plan = self.reasoning.plan(evidence, discovery_context=discovery.markdown)
        write_text(plan_path, plan.markdown, redact=True)
        record = replace(record, artifacts={**record.artifacts, "plan": str(plan_path)})
        self.run_store.write(worktree, record)
        record = self._transition(worktree, record, RunState.PLAN_COMPLETE, "plan complete")

        revision_prompt = ""
        for attempt_number in range(1, config.max_attempts + 1):
            attempt_dir = run_dir / f"attempt-{attempt_number}"
            prompt_path = attempt_dir / "prompt.md"
            prompt = revision_prompt or compile_execution_prompt(
                task=task,
                discovery_context_path=str(discovery_path),
                plan_path=str(plan_path),
                workspace_root=str(repo),
                worktree_root=str(worktree),
                completion_summary_path=str(completed_path),
            )
            write_text(prompt_path, prompt, redact=True)
            record = self._transition(
                worktree,
                record,
                RunState.EXECUTION_PROMPT_READY,
                f"attempt {attempt_number} prompt ready",
            )

            session_id = f"{run_id}-attempt-{attempt_number}"
            session_dir = attempt_dir / "pi-session"
            record = self._transition(
                worktree,
                record,
                RunState.EXECUTION_RUNNING,
                f"attempt {attempt_number} pi running",
            )
            pi_result = self.pi_runner.run(
                worktree=worktree,
                prompt=prompt,
                session_id=session_id,
                session_dir=session_dir,
                artifact_dir=attempt_dir,
            )
            if pi_result.session_file is None:
                return self._block(
                    worktree,
                    record,
                    "Pi session missing",
                    pi_result.error or "No Pi session JSONL found.",
                    evidence,
                    pi_result=pi_result,
                )

            if get_status_porcelain(worktree):
                record = self._transition(
                    worktree,
                    record,
                    RunState.EXECUTION_NEEDS_CLEAN_COMMIT,
                    "pi exited with dirty worktree",
                )
                pi_result = self.pi_runner.run(
                    worktree=worktree,
                    prompt=config.dirty_exit_prompt,
                    session_id=session_id,
                    session_dir=session_dir,
                    artifact_dir=attempt_dir,
                )
                if pi_result.session_file is None:
                    return self._block(
                        worktree,
                        record,
                        "Pi session missing",
                        pi_result.error or "No Pi session JSONL found.",
                        evidence,
                        pi_result=pi_result,
                    )
                if get_status_porcelain(worktree):
                    return self._block(
                        worktree,
                        record,
                        "Dirty worktree",
                        "Pi exited with uncommitted changes after clean-commit prompt.",
                        evidence,
                        pi_result=pi_result,
                    )

            commit_sha = get_head_commit(worktree)
            diff_path = attempt_dir / "git-diff.patch"
            write_text(diff_path, diff_from_base(worktree, base_commit), redact=True)
            record = self._transition(
                worktree,
                record,
                RunState.EXECUTION_COMMITTED,
                f"attempt {attempt_number} committed",
            )

            vet_result = self.vet_runner.run(
                repo_path=worktree,
                task=task,
                base_commit=base_commit,
                model=config.vet_model,
                history_loader_command=f"bd1-pi-history-loader {pi_result.session_file}",
                artifact_dir=attempt_dir,
                confidence_threshold=config.vet_confidence_threshold,
            )
            attempt = self._attempt_record(
                attempt_number,
                pi_result,
                diff_path,
                commit_sha,
                vet_result,
                review_path="",
                review_verdict="",
                reason=vet_result.outcome,
            )

            if vet_result.exit_code == 10:
                record = self._append_attempt(worktree, record, attempt)
                record = self._transition(
                    worktree,
                    record,
                    RunState.VET_FAILED_WITH_FINDINGS,
                    vet_result.findings_summary,
                )
                self._record_learning(worktree, evidence, record, "vet findings")
                revision_prompt = (
                    "Vet found blocking issues. Resolve them and commit before exit.\n\n"
                    f"{vet_result.findings_summary}"
                )
                write_text(attempt_dir / "vet-revision-prompt.md", revision_prompt)
                continue

            if vet_result.exit_code in {1, 2}:
                record = self._append_attempt(worktree, record, attempt)
                return self._block(
                    worktree,
                    record,
                    "Vet failed",
                    f"Vet failed with exit {vet_result.exit_code}: {vet_result.findings_summary}",
                    evidence,
                )

            record = self._append_attempt(worktree, record, attempt)
            record = self._transition(worktree, record, RunState.VET_PASSED, "vet passed")
            record = self._transition(worktree, record, RunState.REVIEW_RUNNING, "review running")
            review = self.reasoning.review(
                task=task,
                discovery_context=discovery.markdown,
                implementation_plan=plan.markdown,
                pi_completion_summary=pi_result.stdout_path.read_text(encoding="utf-8"),
                command_output_summary=vet_result.stdout_path.read_text(encoding="utf-8"),
                git_diff=diff_path.read_text(encoding="utf-8"),
                vet_json=vet_result.output_path.read_text(encoding="utf-8"),
                workspace_artifacts=evidence.workspace_artifacts,
            )
            review_path = (
                worktree
                / ".artifacts"
                / "reviews"
                / f"{task_slug}-{attempt_number}-{'pass' if review.verdict == 'PASS' else 'fail'}.md"
            )
            write_text(review_path, review.markdown, redact=True)
            record = self._replace_last_attempt_review(
                worktree, record, str(review_path), review.verdict
            )
            if review.verdict != "PASS":
                record = self._transition(worktree, record, RunState.REVIEW_FAILED, "review failed")
                self._record_learning(worktree, evidence, record, "review failed")
                revision_prompt = (
                    "Review failed. Resolve the review issues and commit before exit.\n\n"
                    f"{review.markdown}"
                )
                continue

            write_text(
                completed_path,
                f"# Completed: {task}\n\nCommit: {commit_sha}\nReview: {review_path}\n",
                redact=True,
            )
            record = self._transition(worktree, record, RunState.REVIEW_PASSED, "review passed")
            record = replace(
                record,
                final_verdict="PASS",
                artifacts={**record.artifacts, "completed": str(completed_path)},
            )
            self.run_store.write(worktree, record)
            self._record_learning(worktree, evidence, record, "pass")
            record = self._transition(worktree, record, RunState.COMPLETE, "complete")
            return record

        return self._block(
            worktree,
            record,
            "Max attempts reached",
            f"Max attempts reached ({config.max_attempts}).",
            evidence,
        )

    def _transition(
        self, worktree: Path, record: RunRecord, state: RunState, reason: str
    ) -> RunRecord:
        return self.run_store.transition(worktree, record, state, reason)

    def _append_attempt(
        self, worktree: Path, record: RunRecord, attempt: AttemptRecord
    ) -> RunRecord:
        updated = replace(record, attempts=[*record.attempts, attempt])
        self.run_store.write(worktree, updated)
        return updated

    def _replace_last_attempt_review(
        self, worktree: Path, record: RunRecord, review_path: str, verdict: str
    ) -> RunRecord:
        attempts = list(record.attempts)
        attempts[-1] = replace(attempts[-1], review_path=review_path, review_verdict=verdict)
        updated = replace(record, attempts=attempts)
        self.run_store.write(worktree, updated)
        return updated

    def _attempt_record(
        self,
        number: int,
        pi_result: PiResult,
        diff_path: Path,
        commit_sha: str,
        vet_result: VetResult,
        *,
        review_path: str,
        review_verdict: str,
        reason: str,
    ) -> AttemptRecord:
        return AttemptRecord(
            number=number,
            pi_session_id=pi_result.session_id,
            pi_session_file=str(pi_result.session_file or ""),
            pi_stdout_path=str(pi_result.stdout_path),
            pi_stderr_path=str(pi_result.stderr_path),
            git_diff_path=str(diff_path),
            commit_sha=commit_sha,
            vet_command=" ".join(vet_result.command),
            vet_exit_code=vet_result.exit_code,
            vet_output_path=str(vet_result.output_path),
            review_path=review_path,
            review_verdict=review_verdict,
            state_transition_reason=reason,
        )

    def _block(
        self,
        worktree: Path,
        record: RunRecord,
        title: str,
        details: str,
        evidence: EvidencePackage,
        *,
        pi_result: PiResult | None = None,
    ) -> RunRecord:
        blocker_path = worktree / ".artifacts" / "blockers" / f"{record.run_id}.md"
        write_text(
            blocker_path,
            "\n\n".join(
                [
                    f"# Blocked: {title}",
                    f"Task: {record.task}",
                    f"Run ID: {record.run_id}",
                    f"Base commit: {record.base_commit}",
                    f"Branch: {record.branch}",
                    f"Reason: {details}",
                    f"Pi session: {pi_result.session_file if pi_result else ''}",
                ]
            ),
            redact=True,
        )
        updated = replace(record, blocker_path=str(blocker_path), final_verdict="BLOCKED")
        self.run_store.write(worktree, updated)
        self._record_learning(worktree, evidence, updated, title.lower())
        return self._transition(worktree, updated, RunState.BLOCKED, title)

    def _record_learning(
        self, worktree: Path, evidence: EvidencePackage, record: RunRecord, event: str
    ) -> None:
        output = self.reasoning.learn(evidence, review_markdown=event)
        path = worktree / ".artifacts" / "learning" / f"{record.run_id}-{slugify(event)}.md"
        write_text(path, output.markdown, redact=True)
        ExampleStore(worktree).append_example(
            "learning",
            {"run_id": record.run_id, "event": event, "markdown": output.markdown},
        )


def _ignore_runtime_paths(worktree: Path) -> None:
    common_dir = Path(git(worktree, ["rev-parse", "--git-common-dir"]).stdout.strip())
    if not common_dir.is_absolute():
        common_dir = worktree / common_dir
    exclude_path = common_dir / "info" / "exclude"
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    lines = existing.splitlines()
    changed = False
    for pattern in RUNTIME_EXCLUDES:
        if pattern not in lines:
            lines.append(pattern)
            changed = True
    if changed:
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        exclude_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
