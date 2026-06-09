from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


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
    VET_RUNNING = "VET_RUNNING"
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
    LEARNING_RUNNING = "LEARNING_RUNNING"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"


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
    artifact_policy: str
    dirty_base_policy: str
    require_clean_committed_attempt: bool
    dirty_exit_prompt: str
    worktree_root_policy: str
    pr_command: str = "gh"
    pr_monitor_wait_seconds: int = 600
    max_pr_feedback_attempts: int = 3
    pr_base_branch: str = ""
    pr_draft: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceConfig:
        defaults = {
            "pr_command": "gh",
            "pr_monitor_wait_seconds": 600,
            "max_pr_feedback_attempts": 3,
            "pr_base_branch": "",
            "pr_draft": False,
        }
        return cls(**{**defaults, **data})


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
