# Requirements: Compounding Engineering Pipeline

## Problem statement

Modern AI-assisted coding often collapses into terminal babysitting: the human repeatedly prompts, observes failures, corrects the agent, and carries the tacit learning forward manually. The work may complete, but the system rarely improves from the experience.

This project requires a self-improving engineering pipeline where every task leaves behind durable, reusable knowledge. Mistakes, successful fixes, review findings, validation failures, and PR feedback should be captured, structured, scored, and reapplied to future tasks.

## Core principle

Each unit of engineering work should make subsequent units of work easier, safer, and more deterministic.

The pipeline should not aim for perfect first-attempt autonomy. Instead, it should accept that agents will make mistakes, instrument those mistakes, and turn them into reusable learning.

## Goals

1. Reduce repeated human steering during coding tasks.
2. Preserve useful context from every task, review, and PR cycle.
3. Improve future discovery, planning, execution prompts, review decisions, and learning extraction.
4. Keep coding work isolated in git worktrees.
5. Use real validation, not synthetic confidence.
6. Maintain project-specific architectural alignment through durable `.artifacts/` documentation.
7. Use `.learning/` as reusable memory and `.examples/` as DSPy optimization data.

## Non-goals

1. Replace the coding harness.
2. Trust agent output without independent verification.
3. Dump all memory into every prompt.
4. Create a generic coding agent that ignores project-specific architecture.
5. Optimize for speed over correctness.

## System roles

| Component | Responsibility |
|---|---|
| Workspace profiler | Creates initial project artifacts when a workspace is added. |
| Discovery agent | Builds task-specific context from artifacts, codebase, and learning memory. |
| Planner agent | Converts context into an implementation-ready plan. |
| Pi harness | Executes the coding task in a terminal/worktree. |
| Vet | Independently verifies agent behavior and code changes. |
| Review agent | Performs production-readiness review against the plan and repo standards. |
| Resolve agent | Fixes review or PR feedback. |
| PR agent | Creates PRs, monitors CI/review feedback, and records follow-up issues. |
| Learning agent | Extracts reusable lessons after merge. |
| DSPy programs | Provide typed reasoning modules, metrics, and optimization. |

## Workspace model

A workspace is a local git repository managed by the system.

When a user adds a workspace, they provide:

- Workspace name
- Repository path
- Optional worktree setup script
- Product description
- Optional default branch
- Optional validation commands

On save, the workspace profiler generates `.artifacts/` documentation:

```text
.artifacts/
  architecture.md
  system-patterns.md
  testing.md
  design.md
  rules.md
  product.md
```

These files become the durable project constitution. Agents must read them before acting.

## Task lifecycle

1. User provides a task, issue, or problem statement.
2. System creates an isolated worktree and branch.
3. Setup script runs if configured.
4. Discovery creates `.artifacts/context/<task-name>.md`.
5. Planner creates `.artifacts/plans/<task-name>.md`.
6. Execution prompt compiler creates a Pi prompt from the plan/context/learnings.
7. Pi executes using TDD where meaningful.
8. Vet checks goal adherence, behavior, and code changes.
9. Review agent decides `PASS`, `REVISE`, or `FAIL`.
10. If `REVISE`, system generates a revision prompt and loops execution → vet → review.
11. PR agent creates/updates PR and records CI/review feedback.
12. After merge, learning agent extracts structured learnings and DSPy examples.

## Success criteria

The pipeline is successful when:

- A coding task can move from issue → PR with minimal human steering.
- Every agent output is persisted and traceable.
- Vet and review outputs are machine-readable.
- Merged work creates structured learnings.
- Learnings are retrieved selectively for future tasks.
- DSPy examples accumulate over time.
- Review/revision loops become less frequent as the system learns.
