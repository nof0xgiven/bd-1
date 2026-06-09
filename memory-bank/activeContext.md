# Active Context

## Current Focus

Initial memory bank creation for the bd-1 repo.

This memory bank should replace scattered working context for future agents. Keep it current and remove stale statements instead of appending conflicting notes.

## Recent Changes

- Implemented bd-1 CLI runtime wiring for `run`, `status`, and `feedback`.
- Added a full CLI E2E test with fake Pi and fake Vet.
- Replaced README concept text with current MVP usage.
- Ran a live smoke test against `ava-realtime`; bd-1 reached `COMPLETE`.
- Fixed task worktree hygiene after learning capture so `.examples/learning.jsonl` does not leave completed task worktrees dirty.
- Pushed `ava-realtime/main` after committing meeting bridge, OpenAI realtime, and bd-1 workspace artifacts there.

## Current Branch State

- Repo: `/Users/ava/orca/workspaces/bd-1`
- Branch: `bd-1-cli-mvp`
- Latest bd-1 commit: `2214003 fix: keep bd-1 task worktrees clean after learning`
- Working tree was clean before this memory-bank creation.

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

## Important Patterns And Preferences

- Update or remove stale docs. Do not append contradictory docs.
- Keep edits scoped to the request.
- Prefer focused tests around the behavior being changed.
- Run Vet with `--model flash` unless explicitly told not to.
- Do not run Vet when the user explicitly says not to.
- Use `uv run ...` for bd-1 commands unless the executable is installed globally.

## Next Steps

- Commit this memory bank.
- Decide whether to push the bd-1 branch.
- Decide whether the live smoke task branch should be pushed, preserved locally, or deleted.
- Continue tightening the CLI before adding PR automation.

## Memory Bank Update Rule

When the user says `update memory bank`, review every file under `memory-bank/` before editing. Update existing content in place. Remove stale content.
