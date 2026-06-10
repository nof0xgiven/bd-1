# Active Context

## Current Focus

The 13-task gap-closure pass on branch `bd-1-cli-mvp` is landing: reliability knobs, `bd-1 doctor`, doctrine-rich DSPy signatures, executor contract, focused merge-conflict prompts, sandboxed repo tools, ReAct discovery, agentic profiling, full learning-corpus archival, `bd-1 sync`, and a docs truth pass.

This memory bank replaces scattered working context for future agents. Keep it current and remove stale statements instead of appending conflicting notes.

## Recent Changes

- Added `dspy_num_retries` (LM retries) and `discovery_max_iters` (ReAct iterations) config knobs.
- Registry now re-reads the live `.bd-1.toml` on every lookup, so config edits apply without re-registering.
- Added `bd-1 doctor` (binaries, `gh` >= 2.59, `dspy_model`) and a binary-presence preflight at `bd-1 run` start.
- DSPy signatures now carry doctrine-rich docstrings; the review verdict is binary `PASS`/`FAIL` and any P1/P2 finding forces `FAIL` in code.
- Executor contract enforces TDD, no mocks of the system under test, and a proof-of-work completion summary that flows into the review and the PR body.
- Merge conflicts get a focused fetch-first conflict prompt that separates conflict resolution from mixed PR feedback.
- Discovery runs as `dspy.ReAct` over sandboxed read-only `RepoTools`, with a diagnosable single-shot fallback.
- Workspace profiling is agentic (`ProfileWorkspace` over capped text-only evidence) with a `--profile {agentic,keyword}` flag and visible degradation warnings when it falls back to keywords.
- `bd-1 clean` archives the full learning corpus (run record, transitions, diff, review, Pi session/stdout/stderr, vet output, discovery context, plan, completion, PR feedback) before removing the worktree and branch.
- Added `merge_synced_at` to run records and `bd-1 sync`, which polls `gh pr view` for merged PRs and extracts learnings from the archived corpus exactly once per merge. The sweep tolerates stale records and deregistered workspaces by reporting them in `skipped`.

## Current Implementation Status

- Repo: `/Users/ava/orca/workspaces/bd-1`
- Branch: `bd-1-cli-mvp`
- PR lifecycle is implemented for publish/update, monitoring, feedback artifacts, and feedback loops.
- Merge-triggered learning works via `bd-1 sync` polling; run it periodically (cron/CI). Webhook triggers and merge automation are still future work.

## Active Decisions

- Files are authoritative. SQLite is a rebuildable index.
- Global state defaults to `~/.bd-1`; tests and smoke runs should use `BD1_HOME`.
- `.bd-1.toml` is the workspace config file and is read live on every command.
- Base repos must be clean before `bd-1 run`.
- Task worktrees use task-specific runtime excludes.
- Template reasoning is test-only and enabled by `BD1_REASONING=template`.
- Live DSPy reasoning is the default path.
- Pi must produce a real session JSONL file. Missing Pi sessions block before Vet.
- Vet exit code `0` passes, `10` loops with findings, `1` or `2` blocks.
- `gh` (>= 2.59) is the external runtime dependency for PR publish/update, monitoring, and `bd-1 sync`.
- PR lifecycle config fields are `pr_command`, `pr_monitor_wait_seconds`, `max_pr_monitor_polls`, `max_pr_feedback_attempts`, `pr_base_branch`, `pr_draft`, and `pr_comment_ignore_authors`.
- Learnings stay in the global store `~/.bd-1/learning/<workspace>/` (owner-approved divergence from the original in-repo `.learning/` spec).

## Important Patterns And Preferences

- Update or remove stale docs. Do not append contradictory docs.
- Keep edits scoped to the request.
- Prefer focused tests around the behavior being changed.
- Run Vet with `--model flash` unless explicitly told not to.
- Do not run Vet when the user explicitly says not to.
- Use `uv run ...` for bd-1 commands unless the executable is installed globally.

## Next Steps

- Keep docs aligned with implemented behavior; the original spec docs under `docs/` are framed as historical records.
- Build merge automation when the product scope explicitly includes it.
- Replace `bd-1 sync` polling with webhook-triggered learning when webhook support lands.

## Memory Bank Update Rule

When the user says `update memory bank`, review every file under `memory-bank/` before editing. Update existing content in place. Remove stale content.
