from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from enum import StrEnum
from typing import Any

from bd1.errors import WorkspaceConfigError


class RunState(StrEnum):
    TASK_RECEIVED = "TASK_RECEIVED"
    BASE_VERIFIED = "BASE_VERIFIED"
    WORKTREE_CREATED = "WORKTREE_CREATED"
    DISCOVERY_COMPLETE = "DISCOVERY_COMPLETE"
    PLAN_COMPLETE = "PLAN_COMPLETE"
    EXECUTION_PROMPT_READY = "EXECUTION_PROMPT_READY"
    EXECUTION_RUNNING = "EXECUTION_RUNNING"
    EXECUTION_NEEDS_CLEAN_COMMIT = "EXECUTION_NEEDS_CLEAN_COMMIT"
    EXECUTION_COMMITTED = "EXECUTION_COMMITTED"
    VET_FAILED_WITH_FINDINGS = "VET_FAILED_WITH_FINDINGS"
    VET_PASSED = "VET_PASSED"
    REVIEW_RUNNING = "REVIEW_RUNNING"
    REVIEW_FAILED = "REVIEW_FAILED"
    REVIEW_PASSED = "REVIEW_PASSED"
    PR_PUBLISHING = "PR_PUBLISHING"
    PR_CREATED = "PR_CREATED"
    PR_MONITORING = "PR_MONITORING"
    PR_FEEDBACK_RECEIVED = "PR_FEEDBACK_RECEIVED"
    PR_READY = "PR_READY"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"


ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.TASK_RECEIVED: frozenset({RunState.BASE_VERIFIED, RunState.BLOCKED}),
    RunState.BASE_VERIFIED: frozenset({RunState.WORKTREE_CREATED, RunState.BLOCKED}),
    RunState.WORKTREE_CREATED: frozenset({RunState.DISCOVERY_COMPLETE, RunState.BLOCKED}),
    RunState.DISCOVERY_COMPLETE: frozenset({RunState.PLAN_COMPLETE, RunState.BLOCKED}),
    RunState.PLAN_COMPLETE: frozenset({RunState.EXECUTION_PROMPT_READY, RunState.BLOCKED}),
    RunState.EXECUTION_PROMPT_READY: frozenset({RunState.EXECUTION_RUNNING, RunState.BLOCKED}),
    RunState.EXECUTION_RUNNING: frozenset(
        {
            RunState.EXECUTION_NEEDS_CLEAN_COMMIT,
            RunState.EXECUTION_COMMITTED,
            RunState.BLOCKED,
        }
    ),
    RunState.EXECUTION_NEEDS_CLEAN_COMMIT: frozenset(
        {RunState.EXECUTION_COMMITTED, RunState.BLOCKED}
    ),
    RunState.EXECUTION_COMMITTED: frozenset(
        {RunState.VET_FAILED_WITH_FINDINGS, RunState.VET_PASSED, RunState.BLOCKED}
    ),
    RunState.VET_FAILED_WITH_FINDINGS: frozenset(
        {RunState.EXECUTION_PROMPT_READY, RunState.BLOCKED}
    ),
    RunState.VET_PASSED: frozenset({RunState.REVIEW_RUNNING, RunState.BLOCKED}),
    RunState.REVIEW_RUNNING: frozenset(
        {RunState.REVIEW_FAILED, RunState.REVIEW_PASSED, RunState.BLOCKED}
    ),
    RunState.REVIEW_FAILED: frozenset({RunState.EXECUTION_PROMPT_READY, RunState.BLOCKED}),
    RunState.REVIEW_PASSED: frozenset({RunState.PR_PUBLISHING, RunState.BLOCKED}),
    RunState.PR_PUBLISHING: frozenset({RunState.PR_CREATED, RunState.BLOCKED}),
    RunState.PR_CREATED: frozenset({RunState.PR_MONITORING, RunState.BLOCKED}),
    RunState.PR_MONITORING: frozenset(
        {RunState.PR_FEEDBACK_RECEIVED, RunState.PR_READY, RunState.BLOCKED}
    ),
    RunState.PR_FEEDBACK_RECEIVED: frozenset({RunState.EXECUTION_PROMPT_READY, RunState.BLOCKED}),
    RunState.PR_READY: frozenset({RunState.COMPLETE, RunState.BLOCKED}),
    RunState.COMPLETE: frozenset(),
    RunState.BLOCKED: frozenset(),
}


@dataclass(frozen=True)
class WorkspaceConfig:
    name: str
    repo_path: str
    default_branch: str
    product_description: str
    setup_script: str
    max_attempts: int
    pi_command: str
    pi_model: str
    pi_provider: str
    vet_command: str
    vet_model: str
    vet_confidence_threshold: float
    dspy_model: str
    dirty_exit_prompt: str
    pr_command: str = "gh"
    pr_monitor_wait_seconds: int = 600
    max_pr_feedback_attempts: int = 3
    max_pr_monitor_polls: int = 6
    pr_base_branch: str = ""
    pr_draft: bool = False
    pr_comment_ignore_authors: list[str] = field(default_factory=list)
    dspy_num_retries: int = 3
    discovery_max_iters: int = 12
    discovery_mcp_servers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceConfig:
        known_keys = {item.name for item in fields(cls)}
        unknown_keys = sorted(set(data) - known_keys)
        if unknown_keys:
            raise WorkspaceConfigError(
                f"Unknown workspace config key(s): {', '.join(unknown_keys)}"
            )
        retries = data.get("dspy_num_retries", 3)
        max_iters = data.get("discovery_max_iters", 12)
        if not isinstance(retries, int) or retries < 0:
            raise WorkspaceConfigError("dspy_num_retries must be an integer >= 0")
        if not isinstance(max_iters, int) or max_iters < 1:
            raise WorkspaceConfigError("discovery_max_iters must be an integer >= 1")
        try:
            return cls(**data)
        except TypeError as exc:
            raise WorkspaceConfigError(
                f"Workspace config is missing required key(s): {exc}"
            ) from exc


@dataclass(frozen=True)
class AttemptRecord:
    number: int
    pi_session_id: str
    pi_session_file: str
    pi_stdout_path: str
    pi_stderr_path: str
    git_diff_path: str
    commit_sha: str
    vet_command: str
    vet_exit_code: int | None
    vet_output_path: str
    review_path: str
    review_verdict: str
    state_transition_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttemptRecord:
        return cls(**data)


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    workspace: str
    task: str
    base_commit: str
    branch: str
    worktree: str
    state: RunState
    created_at: str
    updated_at: str
    artifacts: dict[str, str] = field(default_factory=dict)
    attempts: list[AttemptRecord] = field(default_factory=list)
    final_verdict: str = ""
    blocker_path: str = ""
    feedback_paths: list[str] = field(default_factory=list)
    pr_number: int | None = None
    pr_url: str = ""
    pr_feedback_paths: list[str] = field(default_factory=list)
    pr_complete_path: str = ""
    pr_seen_feedback_keys: list[str] = field(default_factory=list)
    merge_synced_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["attempts"] = [attempt.to_dict() for attempt in self.attempts]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        return cls(
            run_id=data["run_id"],
            workspace=data["workspace"],
            task=data["task"],
            base_commit=data["base_commit"],
            branch=data["branch"],
            worktree=data["worktree"],
            state=RunState(data["state"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            artifacts=dict(data.get("artifacts", {})),
            attempts=[AttemptRecord.from_dict(item) for item in data.get("attempts", [])],
            final_verdict=data.get("final_verdict", ""),
            blocker_path=data.get("blocker_path", ""),
            feedback_paths=list(data.get("feedback_paths", [])),
            pr_number=data.get("pr_number"),
            pr_url=data.get("pr_url", ""),
            pr_feedback_paths=list(data.get("pr_feedback_paths", [])),
            pr_complete_path=data.get("pr_complete_path", ""),
            pr_seen_feedback_keys=list(data.get("pr_seen_feedback_keys", [])),
            merge_synced_at=data.get("merge_synced_at", ""),
        )


@dataclass(frozen=True)
class FeedbackRecord:
    run_id: str
    created_at: str
    outcome: str
    wrong_or_missing: str
    expected: str
    affected_artifact: str
    commit: str
    learning_candidate: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeedbackRecord:
        return cls(**data)


@dataclass(frozen=True)
class LearningRecord:
    id: str
    created_at: str
    status: str
    source_run_id: str
    source_task: str
    category: str
    applies_when: str
    rule: str
    rationale: str
    evidence: list[dict[str, str]]
    tags: list[str]
    confidence: float
    avoid_when: str = ""
    related_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearningRecord:
        return cls(**data)
