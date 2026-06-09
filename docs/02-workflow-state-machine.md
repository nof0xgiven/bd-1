# Workflow State Machine

## States

```text
WORKSPACE_REGISTERED
WORKSPACE_PROFILED
TASK_RECEIVED
WORKTREE_CREATED
DISCOVERY_COMPLETE
PLAN_COMPLETE
EXECUTION_PROMPT_READY
EXECUTION_RUNNING
EXECUTION_COMPLETE
VET_COMPLETE
REVIEW_COMPLETE
REVISION_REQUIRED
PR_CREATED
PR_FEEDBACK_RECEIVED
PR_READY
MERGED
LEARNING_COMPLETE
FAILED
```

## State transitions

| From | To | Trigger |
|---|---|---|
| WORKSPACE_REGISTERED | WORKSPACE_PROFILED | Workspace profiler completes. |
| TASK_RECEIVED | WORKTREE_CREATED | Worktree created and setup succeeds. |
| WORKTREE_CREATED | DISCOVERY_COMPLETE | Discovery context package written. |
| DISCOVERY_COMPLETE | PLAN_COMPLETE | Implementation plan written. |
| PLAN_COMPLETE | EXECUTION_PROMPT_READY | Pi prompt compiled. |
| EXECUTION_PROMPT_READY | EXECUTION_RUNNING | Pi starts. |
| EXECUTION_RUNNING | EXECUTION_COMPLETE | Pi exits and summary is written. |
| EXECUTION_COMPLETE | VET_COMPLETE | Vet output captured and interpreted. |
| VET_COMPLETE | REVIEW_COMPLETE | Review decision written. |
| REVIEW_COMPLETE | REVISION_REQUIRED | Review decision is `REVISE` or PR feedback exists. |
| REVISION_REQUIRED | EXECUTION_PROMPT_READY | Revision prompt compiled. |
| REVIEW_COMPLETE | PR_CREATED | Review decision is `PASS`. |
| PR_CREATED | PR_FEEDBACK_RECEIVED | CI or CodeRabbit feedback found. |
| PR_FEEDBACK_RECEIVED | REVISION_REQUIRED | Feedback requires changes. |
| PR_CREATED | PR_READY | No blocking feedback. |
| PR_READY | MERGED | PR merged. |
| MERGED | LEARNING_COMPLETE | Learning extraction completed. |
| Any | FAILED | Unrecoverable failure or max loop count exceeded. |

## Loop controls

The system must prevent infinite agent loops.

Recommended limits:

```text
max_execution_attempts: 3
max_pr_feedback_attempts: 3
max_total_task_runtime_minutes: configurable
```

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

A task can proceed to PR only when:

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
- Review returns `REVISE`.
- CI fails.
- CodeRabbit or human PR review provides actionable issues.

## Fail criteria

A task fails when:

- Setup script fails and cannot be recovered.
- Pi cannot complete after max attempts.
- Vet repeatedly flags the same issue.
- Review repeatedly fails production readiness.
- Merge conflicts cannot be safely resolved by the PR agent.
- Required external credentials or services are unavailable.
