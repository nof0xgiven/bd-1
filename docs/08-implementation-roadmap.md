# Implementation Roadmap

> **Historical spec.** This document records the original design and is kept as a historical record. Where it conflicts with the implementation, `README.md`, `docs/02-workflow-state-machine.md`, and `docs/06-storage-layout.md` are authoritative. Known divergences: review verdicts are binary `PASS`/`FAIL` (no `REVISE`); learnings and DSPy examples live in the global store `~/.bd-1/learning/<workspace>/`, not in-repo `.learning/`/`.examples/`; merge-triggered learning is `bd-1 sync` polling, not webhooks. See "Intentional divergences from the original spec" in `README.md`.

## Phase 1: Deterministic orchestration

Build the skeleton before adding intelligence.

Deliverables:

- Workspace registration
- Worktree creation
- Setup script execution
- Run record creation
- Artifact persistence
- Manual prompt templates wired to Pi
- Vet invocation
- Review loop
- Automated PR publish/update with GitHub CLI
- PR check and actionable feedback monitoring
- PR feedback loop back to Pi

Exit criteria:

- One task can go through discovery → plan → execute → vet → review → automated PR publish/monitor.
- All artifacts are saved.
- Failed runs leave useful diagnostics.
- `COMPLETE` is reached only after PR feedback is clear.

Current status:

- Implemented for the CLI MVP through `src/bd1/pr.py` and orchestrator states from `REVIEW_PASSED` through `PR_READY`.
- PR artifacts are written under lowercase `.artifacts/pr/`.
- Post-merge learning is implemented as `bd-1 sync` polling (`gh pr view` + `merge_synced_at`); merge automation and webhook triggers remain future work.

## Phase 2: Hardened prompts and contracts

Deliverables:

- Replace current prompts with strict versions in this bundle.
- Enforce output paths.
- Add artifact validation.
- Add loop limits.
- Add branch safety checks.

Exit criteria:

- Agents consistently write expected files.
- Review failures generate usable resolve prompts.

## Phase 3: DSPy Signatures and Modules

Deliverables:

- Implement DSPy Signatures.
- Wrap discovery, planning, review, and learning as DSPy Modules.
- Persist all DSPy inputs/outputs.

Exit criteria:

- DSPy programs produce the same artifact types as prompt templates.
- Orchestrator can swap prompt-only vs DSPy-backed stages.

## Phase 4: Learning extraction

Deliverables:

- Run record schema
- Learning schema
- Learning extractor
- Retrieval index
- Learning relevance ranking

Exit criteria:

- Merged PR creates at least one validated learning or a rejected-observations report.
- Future discovery retrieves relevant learnings.

Merge-triggered learning ships as `bd-1 sync` polling; webhook triggers are not implemented yet.

## Phase 5: Evaluation datasets

Deliverables:

- `.examples/*.jsonl`
- Metrics for discovery/planning/review/learning
- Offline eval runner
- Baseline scoring

Exit criteria:

- Every completed run can generate candidate examples.
- Human overrides can be captured as high-value examples.

## Phase 6: DSPy optimization

Deliverables:

- Compile selected programs with DSPy optimizers.
- Compare compiled vs baseline outputs.
- Promotion policy.
- Versioned compiled programs.

Exit criteria:

- Compiled module only ships when held-out evaluation improves.
- System can roll back to previous compiled program.

## Phase 7: Operational polish

Deliverables:

- Dashboard or CLI run viewer
- Artifact browser
- Learning review queue
- Run analytics
- Failure-mode reporting

Useful metrics:

- Attempts per successful task
- Review fail rate
- PR feedback loop count
- Time to green
- Repeated failure categories
- Learning reuse frequency
- Learning success rate
