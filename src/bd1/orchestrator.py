from __future__ import annotations

import shlex
import shutil
import traceback
from dataclasses import replace
from pathlib import Path

from bd1.artifacts import ensure_workspace_dirs, write_text
from bd1.dspy_programs import DspyReasoningPrograms, ReasoningPrograms
from bd1.errors import Bd1Error
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
from bd1.git import (
    default_branch as git_default_branch,
)
from bd1.learning import (
    ExampleStore,
    LearningStore,
    learning_records_from_output,
)
from bd1.models import AttemptRecord, RunRecord, RunState, WorkspaceConfig
from bd1.paths import global_state_dir, make_run_id, slugify
from bd1.pi import PiResult, PiRunner
from bd1.pr import PrPublication, PrResult, PrRunner
from bd1.run_store import RunStore, now_iso
from bd1.setup_runner import SetupRunner
from bd1.vet import VetResult, VetRunner

RUNTIME_EXCLUDES = (
    ".sessions/",
    ".artifacts/context/",
    ".artifacts/plans/",
    ".artifacts/vet/",
    ".artifacts/reviews/",
    ".artifacts/pr/",
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
        pr_runner: PrRunner | None = None,
        run_store: RunStore | None = None,
    ) -> None:
        self.global_root = Path(global_root) if global_root else global_state_dir()
        self.reasoning = reasoning or DspyReasoningPrograms()
        self.setup_runner = setup_runner or SetupRunner()
        self._pi_runner = pi_runner
        self._vet_runner = vet_runner
        self._pr_runner = pr_runner
        self._using_real_runners = pi_runner is None and vet_runner is None and pr_runner is None
        self.run_store = run_store or RunStore(self.global_root)

    def run(self, config: WorkspaceConfig, task: str) -> RunRecord:
        if self._using_real_runners:
            missing = [
                binary
                for binary in (
                    shlex.split(command)[0]
                    for command in ("git", config.pi_command, config.vet_command, config.pr_command)
                    if command.strip()
                )
                if shutil.which(binary) is None
            ]
            if missing:
                raise Bd1Error(
                    "Missing required executable(s): "
                    + ", ".join(missing)
                    + ". Run `bd-1 doctor` for details."
                )
        pi_runner = self._pi_runner or PiRunner(
            pi_command=config.pi_command,
            pi_model=config.pi_model,
            pi_provider=config.pi_provider,
        )
        vet_runner = self._vet_runner or VetRunner(vet_command=config.vet_command)
        pr_runner = self._pr_runner or PrRunner(
            pr_command=config.pr_command,
            comment_ignore_authors=tuple(config.pr_comment_ignore_authors),
        )

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
        try:
            return self._run_pipeline(
                config=config,
                task=task,
                repo=repo,
                worktree=worktree,
                record=record,
                run_id=run_id,
                branch=branch,
                base_commit=base_commit,
                pi_runner=pi_runner,
                vet_runner=vet_runner,
                pr_runner=pr_runner,
            )
        except Exception as exc:
            return self._block_unexpected(worktree, run_id, task, exc)

    def _learning_store(self, workspace: str) -> LearningStore:
        return LearningStore.for_workspace(self.global_root, workspace)

    def _example_store(self, workspace: str) -> ExampleStore:
        return ExampleStore.for_workspace(self.global_root, workspace)

    def _block_unexpected(
        self, worktree: Path, run_id: str, task: str, exc: Exception
    ) -> RunRecord:
        record = self.run_store.read(worktree / ".sessions" / run_id / "run-record.json")
        if record.state in (RunState.COMPLETE, RunState.BLOCKED):
            return record
        try:
            evidence: EvidencePackage | None = collect_evidence(
                worktree, task=task, learning_store=self._learning_store(record.workspace)
            )
        except Exception:
            evidence = None
        details = "".join(traceback.format_exception(exc)).strip()
        return self._block(
            worktree,
            record,
            f"Unexpected error: {type(exc).__name__}",
            details,
            evidence,
        )

    def _run_pipeline(
        self,
        *,
        config: WorkspaceConfig,
        task: str,
        repo: Path,
        worktree: Path,
        record: RunRecord,
        run_id: str,
        branch: str,
        base_commit: str,
        pi_runner: PiRunner,
        vet_runner: VetRunner,
        pr_runner: PrRunner,
    ) -> RunRecord:
        record = self._transition(worktree, record, RunState.BASE_VERIFIED, "base clean")
        record = self._transition(worktree, record, RunState.WORKTREE_CREATED, "worktree created")

        learning_store = self._learning_store(config.name)
        run_dir = worktree / ".sessions" / run_id
        if config.setup_script:
            setup_result = self.setup_runner.run(worktree, config.setup_script, run_dir)
            if setup_result.exit_code != 0:
                evidence = collect_evidence(worktree, task=task, learning_store=learning_store)
                return self._block(
                    worktree,
                    record,
                    "Setup failed",
                    f"Setup script exited {setup_result.exit_code}.",
                    evidence,
                )

        evidence = collect_evidence(worktree, task=task, learning_store=learning_store)
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
        attempt_number = 0
        execution_attempts = 0
        pr_feedback_attempts = 0
        next_round_is_pr_feedback = False
        review_history_parts: list[str] = []
        final_diff_text = ""
        pr_feedback_text = ""
        while True:
            attempt_number += 1
            if next_round_is_pr_feedback:
                next_round_is_pr_feedback = False
            else:
                execution_attempts += 1
                if execution_attempts > config.max_attempts:
                    return self._block(
                        worktree,
                        record,
                        "Max attempts reached",
                        f"Max attempts reached ({config.max_attempts}).",
                        evidence,
                        review_history="\n\n".join(review_history_parts),
                        final_diff=final_diff_text,
                        pr_feedback=pr_feedback_text,
                    )
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
            pi_result = pi_runner.run(
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
            if pi_result.exit_code != 0:
                return self._block(
                    worktree,
                    record,
                    "Pi failed",
                    _pi_failure_details(pi_result),
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
                cleanup_result = pi_runner.run(
                    worktree=worktree,
                    prompt=config.dirty_exit_prompt,
                    session_id=session_id,
                    session_dir=session_dir,
                    artifact_dir=attempt_dir / "clean-commit",
                )
                if cleanup_result.session_file is None:
                    return self._block(
                        worktree,
                        record,
                        "Pi session missing",
                        cleanup_result.error or "No Pi session JSONL found.",
                        evidence,
                        pi_result=cleanup_result,
                    )
                if cleanup_result.exit_code != 0:
                    return self._block(
                        worktree,
                        record,
                        "Pi failed",
                        _pi_failure_details(cleanup_result),
                        evidence,
                        pi_result=cleanup_result,
                    )
                if get_status_porcelain(worktree):
                    return self._block(
                        worktree,
                        record,
                        "Dirty worktree",
                        "Pi exited with uncommitted changes after clean-commit prompt.",
                        evidence,
                        pi_result=cleanup_result,
                    )

            commit_sha = get_head_commit(worktree)
            if commit_sha == base_commit:
                return self._block(
                    worktree,
                    record,
                    "Pi made no changes",
                    "Pi completed without committing any changes.",
                    evidence,
                    pi_result=pi_result,
                )
            diff_path = attempt_dir / "git-diff.patch"
            final_diff_text = diff_from_base(worktree, base_commit)
            write_text(diff_path, final_diff_text, redact=True)
            record = self._transition(
                worktree,
                record,
                RunState.EXECUTION_COMMITTED,
                f"attempt {attempt_number} committed",
            )
            # Refresh evidence so review and learning see the post-execution worktree,
            # not the snapshot collected before the attempt ran.
            evidence = collect_evidence(worktree, task=task, learning_store=learning_store)

            vet_result = vet_runner.run(
                repo_path=worktree,
                task=task,
                base_commit=base_commit,
                model=config.vet_model,
                history_loader_command=(
                    f"bd1-pi-history-loader {shlex.quote(str(pi_result.session_file))}"
                ),
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
                review_history_parts.append(
                    f"## Attempt {attempt_number} vet findings\n{vet_result.findings_summary}"
                )
                self._safe_record_learning(
                    worktree,
                    evidence,
                    record,
                    "vet findings",
                    review_history="\n\n".join(review_history_parts),
                    final_diff=final_diff_text,
                    pr_feedback=pr_feedback_text,
                )
                revision_prompt = (
                    "Vet found blocking issues. Resolve them and commit before exit.\n\n"
                    f"{vet_result.findings_summary}"
                )
                write_text(attempt_dir / "vet-revision-prompt.md", revision_prompt)
                continue

            if vet_result.exit_code != 0:
                record = self._append_attempt(worktree, record, attempt)
                return self._block(
                    worktree,
                    record,
                    "Vet failed",
                    f"Vet failed with exit {vet_result.exit_code}: {vet_result.findings_summary}",
                    evidence,
                    review_history="\n\n".join(review_history_parts),
                    final_diff=final_diff_text,
                    pr_feedback=pr_feedback_text,
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
            review_history_parts.append(
                f"## Attempt {attempt_number} review ({review.verdict})\n{review.markdown}"
            )
            if review.verdict != "PASS":
                record = self._transition(worktree, record, RunState.REVIEW_FAILED, "review failed")
                self._safe_record_learning(
                    worktree,
                    evidence,
                    record,
                    "review failed",
                    review_history="\n\n".join(review_history_parts),
                    final_diff=final_diff_text,
                    pr_feedback=pr_feedback_text,
                )
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
                artifacts={**record.artifacts, "completed": str(completed_path)},
            )
            self.run_store.write(worktree, record)

            record = self._transition(worktree, record, RunState.PR_PUBLISHING, "publishing PR")
            try:
                publication = pr_runner.publish_or_update(
                    worktree=worktree,
                    task=task,
                    branch=branch,
                    base_branch=config.pr_base_branch
                    or config.default_branch
                    or git_default_branch(repo),
                    run_id=run_id,
                    base_commit=base_commit,
                    completed_path=completed_path,
                    review_path=review_path,
                    draft=config.pr_draft,
                )
            except Bd1Error as exc:
                return self._block(worktree, record, "PR failed", str(exc), evidence)

            record = self._record_pr_publication(worktree, record, publication)
            record = self._transition(
                worktree, record, RunState.PR_CREATED, f"PR #{publication.number}"
            )

            record = self._transition(worktree, record, RunState.PR_MONITORING, "monitoring PR")
            try:
                pr_result = pr_runner.monitor(
                    worktree=worktree,
                    task=task,
                    task_slug=task_slug,
                    publication=publication,
                    branch=branch,
                    feedback_number=pr_feedback_attempts + 1,
                    wait_seconds=config.pr_monitor_wait_seconds,
                    seen_feedback_keys=set(record.pr_seen_feedback_keys),
                    max_polls=config.max_pr_monitor_polls,
                )
            except Bd1Error as exc:
                return self._block(worktree, record, "PR monitoring failed", str(exc), evidence)

            record = self._record_pr_result(worktree, record, pr_result)

            pr_state = pr_result.state.upper()
            if pr_state == "MERGED":
                record = self._transition(worktree, record, RunState.PR_READY, "PR merged")
                record = replace(record, final_verdict="PASS")
                self.run_store.write(worktree, record)
                self._safe_record_learning(
                    worktree,
                    evidence,
                    record,
                    "pr merged",
                    review_history="\n\n".join(review_history_parts),
                    final_diff=final_diff_text,
                    pr_feedback=pr_feedback_text,
                )
                record = self._transition(worktree, record, RunState.COMPLETE, "complete")
                return record

            if pr_state == "CLOSED":
                return self._block(
                    worktree,
                    record,
                    "PR closed",
                    f"PR #{pr_result.number} was closed without merging. "
                    "Not creating a replacement PR; investigate the closure and rerun manually.",
                    evidence,
                    review_history="\n\n".join(review_history_parts),
                    final_diff=final_diff_text,
                    pr_feedback=pr_feedback_text,
                )

            if pr_result.unsettled:
                return self._block(
                    worktree,
                    record,
                    "PR checks did not settle",
                    "PR checks were still pending after "
                    f"{config.max_pr_monitor_polls} monitor poll(s) of "
                    f"{config.pr_monitor_wait_seconds}s each.",
                    evidence,
                    review_history="\n\n".join(review_history_parts),
                    final_diff=final_diff_text,
                    pr_feedback=pr_feedback_text,
                )

            if pr_result.feedback:
                pr_feedback_attempts += 1
                if pr_feedback_attempts > config.max_pr_feedback_attempts:
                    return self._block(
                        worktree,
                        record,
                        "Max PR feedback attempts reached",
                        f"Max PR feedback attempts reached ({config.max_pr_feedback_attempts}).",
                        evidence,
                        review_history="\n\n".join(review_history_parts),
                        final_diff=final_diff_text,
                        pr_feedback=pr_feedback_text,
                    )
                record = self._transition(
                    worktree,
                    record,
                    RunState.PR_FEEDBACK_RECEIVED,
                    f"PR feedback artifact written: {pr_result.artifact_path}",
                )
                pr_feedback_text = Path(pr_result.artifact_path).read_text(encoding="utf-8")
                self._safe_record_learning(
                    worktree,
                    evidence,
                    record,
                    "pr feedback",
                    review_history="\n\n".join(review_history_parts),
                    final_diff=final_diff_text,
                    pr_feedback=pr_feedback_text,
                )
                revision_prompt = pr_feedback_text
                next_round_is_pr_feedback = True
                continue

            record = self._transition(worktree, record, RunState.PR_READY, "PR feedback complete")
            record = replace(record, final_verdict="PASS")
            self.run_store.write(worktree, record)
            record = self._transition(worktree, record, RunState.COMPLETE, "complete")
            self._safe_record_learning(
                worktree,
                evidence,
                record,
                "pass",
                review_history="\n\n".join(review_history_parts),
                final_diff=final_diff_text,
                pr_feedback=pr_feedback_text,
            )
            return record

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

    def _record_pr_publication(
        self, worktree: Path, record: RunRecord, publication: PrPublication
    ) -> RunRecord:
        updated = replace(record, pr_number=publication.number, pr_url=publication.url)
        self.run_store.write(worktree, updated)
        return updated

    def _record_pr_result(
        self, worktree: Path, record: RunRecord, pr_result: PrResult
    ) -> RunRecord:
        feedback_paths = list(record.pr_feedback_paths)
        if pr_result.artifact_path:
            feedback_paths.append(pr_result.artifact_path)
        seen_feedback_keys = list(
            dict.fromkeys(
                [*record.pr_seen_feedback_keys, *(item.key for item in pr_result.feedback)]
            )
        )
        updated = replace(
            record,
            pr_number=pr_result.number,
            pr_url=pr_result.url,
            pr_feedback_paths=feedback_paths,
            pr_complete_path=pr_result.complete_artifact_path or record.pr_complete_path,
            pr_seen_feedback_keys=seen_feedback_keys,
        )
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
        evidence: EvidencePackage | None,
        *,
        pi_result: PiResult | None = None,
        review_history: str = "",
        final_diff: str = "",
        pr_feedback: str = "",
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
        updated = self._transition(worktree, updated, RunState.BLOCKED, title)
        self._safe_record_learning(
            worktree,
            evidence,
            updated,
            title.lower(),
            review_history=review_history,
            final_diff=final_diff,
            pr_feedback=pr_feedback,
        )
        return updated

    def _safe_record_learning(
        self,
        worktree: Path,
        evidence: EvidencePackage | None,
        record: RunRecord,
        event: str,
        *,
        review_history: str = "",
        final_diff: str = "",
        pr_feedback: str = "",
    ) -> None:
        if evidence is None:
            return
        try:
            self._record_learning(
                worktree,
                evidence,
                record,
                event,
                review_history=review_history,
                final_diff=final_diff,
                pr_feedback=pr_feedback,
            )
        except Exception as exc:
            note_path = (
                worktree / ".artifacts" / "learning" / f"{record.run_id}-{slugify(event)}-error.md"
            )
            try:
                write_text(
                    note_path,
                    f"Learning capture failed for event '{event}': {exc}\n",
                    redact=True,
                )
            except OSError:
                return

    def _record_learning(
        self,
        worktree: Path,
        evidence: EvidencePackage,
        record: RunRecord,
        event: str,
        *,
        review_history: str = "",
        final_diff: str = "",
        pr_feedback: str = "",
    ) -> None:
        review_markdown = f"{event}\n\n{review_history}" if review_history else event
        output = self.reasoning.learn(
            evidence,
            review_markdown=review_markdown,
            final_diff=final_diff,
            pr_feedback=pr_feedback,
        )
        # Per-run markdown artifact stays in the worktree for traceability.
        path = worktree / ".artifacts" / "learning" / f"{record.run_id}-{slugify(event)}.md"
        write_text(path, output.markdown, redact=True)
        # Durable learnings and examples live in the global per-workspace store.
        learning_store = self._learning_store(record.workspace)
        for learning in learning_records_from_output(
            output.learnings, run_id=record.run_id, task=record.task, event=slugify(event)
        ):
            learning_store.save_learning(learning)
        self._example_store(record.workspace).append_example(
            "learning",
            {"run_id": record.run_id, "event": event, "markdown": output.markdown},
        )


def _ignore_runtime_paths(worktree: Path) -> None:
    git_dir = Path(git(worktree, ["rev-parse", "--absolute-git-dir"]).stdout.strip())
    exclude_path = git_dir / "info" / "exclude"
    git(worktree, ["config", "extensions.worktreeConfig", "true"])
    git(worktree, ["config", "--worktree", "core.excludesFile", str(exclude_path)])
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


def _pi_failure_details(pi_result: PiResult) -> str:
    parts = [f"Pi exited with exit {pi_result.exit_code}."]
    if pi_result.error:
        parts.append(pi_result.error)
    stderr = pi_result.stderr_path.read_text(encoding="utf-8").strip()
    if stderr:
        parts.append(stderr)
    return " ".join(parts)
