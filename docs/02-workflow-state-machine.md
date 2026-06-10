# Workflow State Machine

## States

```text
TASK_RECEIVED
BASE_VERIFIED
WORKTREE_CREATED
DISCOVERY_COMPLETE
PLAN_COMPLETE
EXECUTION_PROMPT_READY
EXECUTION_RUNNING
EXECUTION_NEEDS_CLEAN_COMMIT
EXECUTION_COMMITTED
VET_FAILED_WITH_FINDINGS
VET_PASSED
REVIEW_RUNNING
REVIEW_FAILED
REVIEW_PASSED
PR_PUBLISHING
PR_CREATED
PR_MONITORING
PR_FEEDBACK_RECEIVED
PR_READY
COMPLETE
BLOCKED
```

## State transitions

| From | To | Trigger |
|---|---|---|
| TASK_RECEIVED | BASE_VERIFIED | Base repo is clean and the base commit is recorded. |
| BASE_VERIFIED | WORKTREE_CREATED | Worktree created and setup succeeds. |
| WORKTREE_CREATED | DISCOVERY_COMPLETE | Discovery context package written. |
| DISCOVERY_COMPLETE | PLAN_COMPLETE | Implementation plan written. |
| PLAN_COMPLETE | EXECUTION_PROMPT_READY | Pi prompt compiled. |
| EXECUTION_PROMPT_READY | EXECUTION_RUNNING | Pi starts. |
| EXECUTION_RUNNING | EXECUTION_NEEDS_CLEAN_COMMIT | Pi exits with uncommitted work in the task worktree. |
| EXECUTION_NEEDS_CLEAN_COMMIT | EXECUTION_COMMITTED | Cleanup prompt resumes the same Pi session and commits the remaining work. |
| EXECUTION_RUNNING | EXECUTION_COMMITTED | Pi exits and committed changes are available. |
| EXECUTION_COMMITTED | VET_FAILED_WITH_FINDINGS | Vet runs on the captured Pi history and returns actionable findings. |
| VET_FAILED_WITH_FINDINGS | EXECUTION_PROMPT_READY | Vet findings prompt is compiled for the next execution attempt. |
| EXECUTION_COMMITTED | VET_PASSED | Vet runs on the captured Pi history and passes. |
| VET_PASSED | REVIEW_RUNNING | Review gate starts. |
| REVIEW_RUNNING | REVIEW_FAILED | Review decision is `FAIL` (binary verdict; review loops back to execution). |
| REVIEW_FAILED | EXECUTION_PROMPT_READY | Review revision prompt is compiled. |
| REVIEW_RUNNING | REVIEW_PASSED | Review decision is `PASS`. |
| REVIEW_PASSED | PR_PUBLISHING | Review decision is `PASS`. |
| PR_PUBLISHING | PR_CREATED | Branch pushed and PR created or updated. |
| PR_CREATED | PR_MONITORING | PR metadata is available. |
| PR_MONITORING | PR_FEEDBACK_RECEIVED | CI, CodeRabbit, or human review feedback requires changes. |
| PR_FEEDBACK_RECEIVED | EXECUTION_PROMPT_READY | Consolidated PR feedback prompt is used for the next execution attempt. |
| PR_MONITORING | PR_READY | No blocking CI or review feedback remains. |
| PR_READY | COMPLETE | PR feedback artifact is marked complete. |
| Any non-terminal state | BLOCKED | Unrecoverable failure or max loop count exceeded. |

`COMPLETE` and `BLOCKED` are terminal. The legal transitions above are enforced at
runtime by `ALLOWED_TRANSITIONS` in `src/bd1/models.py`; any other jump raises an
error instead of being recorded.

## Loop controls

The system must prevent infinite agent loops.

Recommended limits:

```text
max_execution_attempts: 3
max_pr_feedback_attempts: 3
max_total_task_runtime_minutes: configurable
```

Execution, vet, and review failures count against `max_attempts`. PR feedback
rounds count only against `max_pr_feedback_attempts`; they do not consume the
execution budget.

If the loop limit is reached, the orchestrator should write a failure report containing:

- Task
- Run ID
- Base commit
- Current branch
- Last plan
- Last diff
- Last Vet output
- Last review decision
- Reason for stopping
- Recommended human action

## Pass criteria

A task can proceed to PR publishing only when:

1. Pi completed successfully.
2. Required quality gates passed.
3. Vet produced no blocking issues.
4. Review decision is `PASS`.
5. Completion summary exists.
6. Diff is limited to scoped files unless explicitly justified.

## Revision criteria

A task loops back to execution when:

- Vet identifies goal mismatch.
- Vet identifies suspicious agent behavior.
- Review returns `FAIL`.
- CI fails.
- CodeRabbit or human PR review provides actionable issues.

## Fail criteria

A task fails when:

- Setup script fails and cannot be recovered.
- Pi cannot complete after max attempts.
- Vet repeatedly flags the same issue.
- Review repeatedly fails production readiness.
- Merge conflicts or unknown mergeability require human action.
- Required external credentials or services are unavailable.
