# Agent Contracts

> **Historical spec.** This document records the original design and is kept as a historical record. Where it conflicts with the implementation, `README.md`, `docs/02-workflow-state-machine.md`, and `docs/06-storage-layout.md` are authoritative. Known divergences: review verdicts are binary `PASS`/`FAIL` (no `REVISE`); learnings and DSPy examples live in the global store `~/.bd-1/learning/<workspace>/`, not in-repo `.learning/`/`.examples/`; merge-triggered learning is `bd-1 sync` polling, not webhooks. See "Intentional divergences from the original spec" in `README.md`.

## Contract philosophy

Every agent should have:

- Clear input artifacts
- Clear output artifacts
- Non-interactive behavior
- Explicit permissions
- Strict write boundaries
- Machine-readable decisions where possible

## Discovery agent

Inputs:

- Task description
- `.artifacts/*`
- relevant `.learning/*`
- repo read access
- Exa Code / Context7 when needed

Permissions:

- Read-only

Output:

```text
.artifacts/context/<task-name>.md
```

Contract:

- Must include source-of-truth evidence.
- Must include exact file paths and line ranges.
- Must surface ambiguities.
- Must not propose unsupported implementation choices.

## Planner agent

Inputs:

- Task description
- Discovery context package
- Workspace artifacts
- Relevant learnings

Permissions:

- Write plan only

Output:

```text
.artifacts/plans/<task-name>.md
```

Contract:

- Must not write production code.
- Must provide file-by-file impact.
- Must provide implementation order.
- Must explicitly state assumptions.

## Execute agent

Inputs:

- Implementation plan
- Context package
- Compiled Pi prompt

Permissions:

- Modify scoped files only
- Commit changes

Output:

```text
.artifacts/completed/<task-name>.md
```

Contract:

- Must verify not on main.
- Must use TDD for meaningful changes.
- Must run applicable quality gates.
- Must provide proof of work.

## Vet interpreter

Inputs:

- Raw Vet output
- Task
- Plan
- Diff

Permissions:

- Read-only

Output:

```json
{
  "passed": true,
  "blockers": [],
  "warnings": [],
  "required_revisions": [],
  "confidence": 0.0
}
```

## Review agent

Inputs:

- Plan
- Coder summary
- Diff against main
- Test output
- Vet interpretation
- Workspace artifacts

Permissions:

- Read-only

Output:

```text
.artifacts/reviews/<task-name>-<n>-<pass|fail>.md
```

Contract:

- Binary production-readiness decision.
- Fail when in doubt.
- Do not design unrelated future work.
- Do not modify files.

## Resolve agent

Inputs:

- Review issue document or PR feedback document
- Existing plan/context

Permissions:

- Modify only scoped files needed to resolve feedback
- Commit changes

Output:

```text
.artifacts/review/<task-name>-<n>-resolved.md
```

## PR agent

Inputs:

- Branch/worktree
- Completion summary
- Review result

Permissions:

- Create/update PR
- Read CI/review comments
- Resolve merge conflicts only when safe

Output:

```text
.artifacts/pr/<task-name>-<n>.md
.artifacts/pr/<task-name>-<n>-complete.md
```

## Learning agent

Inputs:

- Run record
- Pi transcript
- Vet output
- Review history
- PR comments
- CI results
- Final diff

Permissions:

- Write `.learning/` and `.examples/`

Output:

```text
.learning/learnings/<id>.json
.examples/*.jsonl
```
