# Product Context

## Why This Exists

AI coding work often completes without compounding. The human remembers what went wrong, which checks mattered, and which instructions worked, but the toolchain forgets.

bd-1 exists to make each task produce reusable context:

- What the task asked for.
- What the repo already said.
- What Pi did.
- What Vet found.
- What review decided.
- What should be learned for the next task.

## Problems Solved

- Reduces repeated human steering for similar tasks.
- Keeps task work isolated from the source repo by using git worktrees.
- Records run state in files that can be inspected without a database.
- Gives Vet a real Pi transcript through a history loader instead of fabricated context.
- Captures feedback and learning events after a run.
- Keeps runtime artifacts out of normal commits.

## User Experience Goals

- A user can add a workspace with one command.
- A user can run `bd-1 run "task"` from inside a configured repo.
- A user can run `bd-1 run --workspace name "task"` from elsewhere.
- A user can inspect a run with `bd-1 status <run-id>`.
- A user can add correction feedback with `bd-1 feedback <run-id> ...`.
- Failures should produce blocker artifacts with enough detail for a human to act.

## Expected Product Feel

bd-1 should feel like a local engineering tool, not a chat interface.

- Clear CLI commands.
- Explicit file paths.
- Deterministic state transitions.
- Conservative failure behavior.
- No silent mutation of a dirty base repo.
- No hidden database-only state.

## Proof So Far

The MVP completed a live smoke run against `/Users/ava/main/projects/ava-realtime`:

- Registered the workspace.
- Created a task worktree.
- Invoked Pi.
- Captured the Pi session.
- Ran Vet with exit code `0`.
- Produced a review verdict of `PASS`.
- Completed with final state `COMPLETE`.
