# Suggested Architecture

> **Historical spec.** This document records the original design and is kept as a historical record. Where it conflicts with the implementation, `README.md`, `docs/02-workflow-state-machine.md`, and `docs/06-storage-layout.md` are authoritative. Known divergences: review verdicts are binary `PASS`/`FAIL` (no `REVISE`); learnings and DSPy examples live in the global store `~/.bd-1/learning/<workspace>/`, not in-repo `.learning/`/`.examples/`; merge-triggered learning is `bd-1 sync` polling, not webhooks. See "Intentional divergences from the original spec" in `README.md`.

## Architectural thesis

The system should separate performance, judgment, and learning.

```text
Pi performs.
Vet judges behavior and correctness.
DSPy structures reasoning, decisions, examples, and optimization.
```

Pi should not become the brain. It should remain the coding executor. DSPy should own the reasoning programs that generate task context, plans, execution prompts, review decisions, and structured learnings.

## High-level architecture

```text
┌────────────────────┐
│ User task / issue  │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ Orchestrator        │
│ run_task()          │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ Worktree Manager    │
│ branch + setup      │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ DSPy Discovery      │◀── .artifacts + .learning
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ DSPy Planner        │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ DSPy Prompt Compiler│
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ Pi Coding Harness   │
│ TDD / edit / test   │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ Vet                 │
│ independent check   │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ DSPy Review Decision│
│ PASS/REVISE/FAIL    │
└─────┬─────────┬─────┘
      │         │
      │ PASS    │ REVISE
      ▼         ▼
┌──────────┐  ┌──────────────────┐
│ PR Agent │  │ DSPy Revision     │
└────┬─────┘  │ Prompt Compiler   │
     │        └────────┬─────────┘
     ▼                 │
┌──────────┐           │
│ Merge    │           └── back to Pi
└────┬─────┘
     ▼
┌────────────────────┐
│ DSPy Learning       │
│ learnings + examples│
└────────────────────┘
```

## Runtime services

### Orchestrator

Coordinates the state machine. It should not contain prompt logic.

Responsibilities:

- Create run records.
- Create worktrees.
- Invoke DSPy programs.
- Invoke Pi and Vet.
- Persist artifacts.
- Route `PASS`, `REVISE`, and `FAIL` decisions.
- Trigger PR and learning cycles.

### Worktree manager

Responsibilities:

- Verify clean main/default branch.
- Create task branch and worktree.
- Run workspace setup script.
- Track base commit.
- Prevent accidental writes on main.
- Clean up failed or completed worktrees according to policy.

### Artifact store

Responsibilities:

- Read/write `.artifacts/` files.
- Version task-specific artifacts.
- Persist context packages, plans, completion summaries, reviews, PR feedback, and learning reports.

### Learning store

Responsibilities:

- Store structured learning JSON.
- Retrieve relevant learnings by task/domain/files/tags.
- Avoid injecting stale or low-confidence learnings blindly.
- Track learning usefulness over time.

### Example store

Responsibilities:

- Convert successful runs into DSPy training/evaluation examples.
- Store examples by program type: discovery, planning, review, learning.
- Keep examples linked to run IDs and source artifacts.

## DSPy programs

| Program | Input | Output |
|---|---|---|
| WorkspaceProfiler | repo + product description | initial `.artifacts/` docs |
| DiscoveryProgram | task + repo context + artifacts + learnings | context package |
| PlannerProgram | task + context package + rules | implementation plan |
| PiPromptCompiler | plan + context + rules + learnings | strict Pi execution prompt |
| VetInterpreter | task + plan + diff + vet output | structured vet result |
| ReviewDecision | plan + diff + tests + vet result | PASS/REVISE/FAIL + revision prompt |
| LearningExtractor | full run record | structured learnings + DSPy examples |

## Boundaries

### DSPy should not

- Edit files directly.
- Run terminal commands directly unless inside a controlled tool wrapper.
- Replace Vet.
- Replace Pi.
- Hide uncertainty.

### Pi should not

- Decide whether work is production-ready.
- Invent project architecture.
- Ignore discovery or plan artifacts.
- Continue after quality gates fail.

### Review should not

- Design new features.
- Rewrite the plan.
- Pass work that needs near-term cleanup.

## Why this shape works

This architecture lets each component remain good at one thing:

- Pi is good at doing work.
- Vet is good at independent verification.
- DSPy is good at typed reasoning programs and optimization.
- `.artifacts/` preserves project-specific architecture.
- `.learning/` preserves reusable experience.
- `.examples/` turns experience into measurable improvement.
