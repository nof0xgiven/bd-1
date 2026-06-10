# Active Context

## Current Focus

Document the current bd-1 PR lifecycle implementation in the docs and memory bank.

This memory bank replaces scattered working context for future agents. Keep it current and remove stale statements instead of appending conflicting notes.

## Recent Changes

- Implemented bd-1 CLI runtime wiring for `run`, `status`, and `feedback`.
- Added a full CLI E2E test with fake Pi and fake Vet.
- Replaced README concept text with current MVP usage.
- Ran a live smoke test against `ava-realtime`; bd-1 reached `COMPLETE`.
- Moved learnings and DSPy examples to the global per-workspace store under `<BD1_HOME>/learning/<workspace>/`; task worktrees only keep per-run learning markdown under `.artifacts/learning/`.
- Pushed `ava-realtime/main` after committing meeting bridge, OpenAI realtime, and bd-1 workspace artifacts there.
- Added `src/bd1/pr.py` as the GitHub CLI PR adapter.
- Added PR publish/update after `REVIEW_PASSED`.
- Added PR check and actionable review feedback monitoring.
- Added PR feedback artifacts under lowercase `.artifacts/pr/`.
- Added PR feedback loops back to Pi and completion only after PR feedback is clear.

## Current Implementation Status

- Repo: `/Users/ava/orca/workspaces/bd-1`
- Branch: `bd-1-cli-mvp`
- PR lifecycle work is implemented for publish/update, monitoring, feedback artifacts, and feedback loops.
- Merge automation and webhook/post-merge learning are still future work.

## Active Decisions

- Files are authoritative. SQLite is a rebuildable index.
- Global state defaults to `~/.bd-1`; tests and smoke runs should use `BD1_HOME`.
- `.bd-1.toml` is the workspace config file.
- Base repos must be clean before `bd-1 run`.
- Task worktrees use task-specific runtime excludes.
- Template reasoning is test-only and enabled by `BD1_REASONING=template`.
- Live DSPy reasoning is the default path.
- Pi must produce a real session JSONL file. Missing Pi sessions block before Vet.
- Vet exit code `0` passes, `10` loops with findings, `1` or `2` blocks.
- `gh` is the external runtime dependency for PR publish/update and monitoring.
- PR lifecycle config fields are `pr_command`, `pr_monitor_wait_seconds`, `max_pr_feedback_attempts`, `pr_base_branch`, and `pr_draft`.

## Important Patterns And Preferences

- Update or remove stale docs. Do not append contradictory docs.
- Keep edits scoped to the request.
- Prefer focused tests around the behavior being changed.
- Run Vet with `--model flash` unless explicitly told not to.
- Do not run Vet when the user explicitly says not to.
- Use `uv run ...` for bd-1 commands unless the executable is installed globally.

## Next Steps

- Keep docs aligned with the implemented PR lifecycle states.
- Build merge automation when the product scope explicitly includes it.
- Add webhook/post-merge learning when the learning pipeline is ready for that trigger.

## Memory Bank Update Rule

When the user says `update memory bank`, review every file under `memory-bank/` before editing. Update existing content in place. Remove stale content.
