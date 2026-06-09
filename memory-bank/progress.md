# Progress

## Current Status

bd-1 has a working CLI MVP.

The repo has passed local verification after the latest hygiene fix:

- `uv run ruff check src tests`
- `uv run ruff format --check src tests`
- `uv run pytest -q` with `79 passed`
- Vet for the hygiene fix with `--model flash`

## What Works

- Package scaffold and CLI entrypoints.
- Workspace registration and profiling.
- `.bd-1.toml` workspace config.
- Global workspace registry.
- Run records and transitions.
- SQLite run index refresh through `bd-1 status`.
- Dirty base repo rejection.
- Task worktree creation.
- Setup script execution.
- Discovery and plan artifact creation.
- Pi subprocess invocation.
- Pi JSONL history loader for Vet.
- Vet subprocess invocation and exit-code handling.
- Review pass/fail loop.
- Max-attempt blocker behavior.
- Feedback recording.
- Learning and example capture.
- Full CLI E2E with fake Pi and fake Vet.
- Live smoke run against `ava-realtime` with final state `COMPLETE`.
- Task worktree hygiene after learning capture.

## Recent Proof

Live smoke against `/Users/ava/main/projects/ava-realtime`:

- Base commit: `84dff416a7a294885488fea5e6e0be60d608fbcb`
- Task commit: `3200678d6af8c041c0902d68e62fe6a99045c875`
- Final state: `COMPLETE`
- Final verdict: `PASS`
- Vet exit code: `0`
- Vet output: `{"issues": []}`
- Review verdict: `PASS`
- Diff: `README.md | 4 ++++`

## What Is Left To Build

- PR creation and PR monitoring.
- Merge handling.
- Hosted CI polling.
- Richer learning retrieval and confidence handling.
- Better workspace profiling quality.
- Better reporting for long-running Pi executions.
- Cleanup or retention policy for smoke/task worktrees.
- Documentation for operational workflows beyond README.

## Known Issues And Risks

- Live DSPy behavior depends on configured model credentials.
- Old docs under `docs/` still describe some future architecture, including PR automation that is not yet implemented.
- The current learning extractor can produce noisy learning content if workspace artifacts contain unrelated prior context.
- Global `bd-1` executable may not be installed; `uv run bd-1` is the reliable local path.

## Decision History

- Files are authoritative; SQLite is rebuildable.
- Task runtime state stays out of normal commits.
- Workspace profile artifacts are durable and reviewable.
- Template reasoning is for tests and fake-tool E2E only.
- Vet receives real Pi history through `bd1-pi-history-loader`.
- Completed task worktrees must be clean even after learning capture.
