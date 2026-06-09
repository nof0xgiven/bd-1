# Compounding Engineering Pipeline

A self-improving coding pipeline built around three separate concerns:

- **Pi** performs terminal-based coding work.
- **Vet** independently checks agent behavior and code correctness.
- **DSPy** owns the reasoning programs, scoring, examples, and optimization loop.

The system is designed around one principle:

> Every completed unit of engineering work must make future engineering work easier, safer, and more predictable.

## Recommended structure

```text
.compound/
  workspaces/
  runs/
  compiled-dspy/

workspace-root/
  .artifacts/
    architecture.md
    system-patterns.md
    testing.md
    design.md
    rules.md
    product.md
    context/
    plans/
    completed/
    reviews/
    pr/
  .learning/
    learnings/
    index.json
  .examples/
    discovery.jsonl
    planning.jsonl
    review.jsonl
    learning.jsonl
  .sessions/
```

## Execution lifecycle

```text
Workspace saved
  → Workspace profiler creates durable artifacts

Task submitted
  → Worktree created
  → Discovery context built
  → Implementation plan generated
  → Pi execution prompt compiled
  → Pi executes with TDD
  → Vet checks behavior and diff
  → Review decides PASS / REVISE / FAIL
  → Loop until PASS
  → PR created and monitored
  → Merge triggers learning extraction
  → Learning saved + example generated for DSPy optimization
```

## Files in this bundle

```text
docs/
  00-requirements.md
  01-system-architecture.md
  02-workflow-state-machine.md
  03-dspy-implementation.md
  04-learning-system.md
  05-evaluation-and-optimization.md
  06-storage-layout.md
  07-agent-contracts.md
  08-implementation-roadmap.md

prompts/
  discovery.md
  planner.md
  execute.md
  vet_interpreter.md
  review.md
  resolve.md
  pr.md
  learning.md
  workspace_profiler.md

schemas/
  learning.schema.json
  run-record.schema.json
  review-decision.schema.json
  workspace-artifacts.schema.json

examples/
  run-record.example.json
  learning.example.json

originals/
  Your original uploaded files, unchanged.
```
