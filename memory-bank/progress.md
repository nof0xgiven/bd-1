# Progress

## Current Status

bd-1 has a working CLI MVP covering the full loop: worktree isolation, ReAct discovery, Pi execution under an executor contract, Vet, a binary PASS/FAIL review gate, PR publish/monitor/feedback, run cleanup with full corpus archival, and merge-triggered learning via `bd-1 sync`.

The 13-task gap-closure pass on `bd-1-cli-mvp` is landing. Local verification:

- `uv run ruff check`
- `uv run ruff format --check`
- `uv run pytest -q` (277 passing)

## What Works

- Package scaffold and CLI entrypoints.
- Workspace registration and agentic profiling (`ProfileWorkspace` with keyword fallback, `--profile {agentic,keyword}`, visible degradation warnings).
- `.bd-1.toml` workspace config, read live on every command.
- Reliability knobs: `dspy_num_retries`, `discovery_max_iters`, `max_pr_monitor_polls`, `pr_comment_ignore_authors`.
- `bd-1 doctor` environment checks and the `bd-1 run` binary preflight.
- Global workspace registry.
- Run records and enforced state transitions.
- SQLite run index refresh through `bd-1 status`.
- Dirty base repo rejection.
- Task worktree creation.
- Setup script execution.
- Tool-using ReAct discovery over sandboxed read-only RepoTools, with a diagnosable single-shot fallback.
- Plan artifact creation.
- Pi subprocess invocation under the executor contract (TDD, no mocks of the system under test, proof-of-work completion summary).
- Pi JSONL history loader for Vet.
- Vet subprocess invocation and exit-code handling.
- Binary PASS/FAIL review gate; P1/P2 findings force FAIL in code.
- Completion summary flowing into review and the PR body.
- PR branch push and create/update through `gh`.
- PR check and actionable review feedback monitoring.
- Focused fetch-first merge-conflict prompts that separate conflicts from mixed feedback.
- PR feedback artifacts under `.artifacts/pr/`.
- PR feedback loop back to Pi.
- Final `COMPLETE` state only after PR feedback is clear.
- Max-attempt blocker behavior.
- Feedback recording.
- Learning and example capture into the global store `~/.bd-1/learning/<workspace>/`.
- `bd-1 clean` archiving the full learning corpus before removing worktree and branch.
- `bd-1 sync` merge-triggered learning with `merge_synced_at` stamping; the sweep skips (not aborts on) stale records and deregistered workspaces.
- Full CLI E2E with fake Pi, Vet, and gh.
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

- Merge automation.
- Webhook-triggered learning (today: run `bd-1 sync` on a schedule).
- Richer learning retrieval and confidence handling.
- Better reporting for long-running Pi executions.
- Retention policy for archived runs under `~/.bd-1/runs/`.
- Documentation for operational workflows beyond README.

## Known Issues And Risks

- Live DSPy behavior depends on configured model credentials.
- Merge automation and webhook triggers are still future architecture; `bd-1 sync` covers post-merge learning by polling.
- PR lifecycle depends on `gh` (>= 2.59) being installed, authenticated, and authorized for the target repo.
- The current learning extractor can produce noisy learning content if workspace artifacts contain unrelated prior context.
- Global `bd-1` executable may not be installed; `uv run bd-1` is the reliable local path.

## Decision History

- Files are authoritative; SQLite is rebuildable.
- Task runtime state stays out of normal commits.
- Workspace profile artifacts are durable and reviewable.
- Template reasoning is for tests and fake-tool E2E only.
- Vet receives real Pi history through `bd1-pi-history-loader`.
- Completed task worktrees must be clean even after learning capture.
- PR artifacts use lowercase `.artifacts/pr/`.
- PR feedback is de-duplicated and tracked in run records before looping back to Pi.
- Review verdicts are binary PASS/FAIL; REVISE was removed from the design.
- Learnings live in the global store, not in-repo `.learning/` (owner-approved divergence).
- Merge-triggered learning is `bd-1 sync` polling, a deliberate stand-in for webhooks (backlog).
