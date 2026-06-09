# Project Brief

## Project

bd-1 is a local compounding engineering pipeline CLI.

The executable is `bd-1`; the Python package is `bd1`.

## Core Goal

Run a coding task through an isolated local workflow:

1. Register a git workspace.
2. Create durable workspace artifacts.
3. Create an isolated task worktree.
4. Build discovery and plan artifacts.
5. Invoke Pi as the executor.
6. Run Vet as an independent verifier.
7. Run a review gate.
8. Publish or update the task PR after local review passes.
9. Monitor PR checks and actionable review feedback.
10. Loop PR feedback back to Pi when changes are required.
11. Persist run records, attempts, artifacts, feedback, and learning examples.

Each completed task should leave behind structured evidence that makes later work easier to scope, verify, and improve.

## Scope

Current MVP scope:

- Python + uv CLI.
- File-authoritative run state.
- Global state in `~/.bd-1` or `BD1_HOME`.
- Workspace-local config in `.bd-1.toml`.
- Workspace-local durable artifacts in `.artifacts/`, `.learning/`, and `.examples/`.
- Raw sessions and rebuildable indexes ignored from normal commits.
- Pi execution via `pi -p`.
- Vet execution via `vet`.
- Pi session conversion through `bd1-pi-history-loader`.
- PR publish, update, check monitoring, and actionable feedback capture through GitHub CLI `gh`.
- PR feedback artifacts under `.artifacts/pr/`.
- Template reasoning for deterministic tests through `BD1_REASONING=template`.
- Live DSPy reasoning by default when configured.

## Out Of Scope For Current MVP

- Hosted service operation.
- Merge automation.
- Webhook/post-merge learning automation.
- Long-term optimization training runs.
- Replacing Pi or Vet.
- Trusting agent output without independent verification.

## Source Of Truth

This file defines current project scope. Other memory-bank files should stay consistent with it.

When scope changes, update this file first, then update the dependent memory-bank files.
