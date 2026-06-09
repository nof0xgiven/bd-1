# DSPy Implementation Guide

## Principle

DSPy should implement typed language-model programs, not loose prompt strings. Each reasoning step should be represented as a Signature and wrapped by a Module.

The pipeline should compile and improve these modules over time using examples and metrics.

## Program inventory

```text
dspy_programs/
  workspace_profiler.py
  discovery.py
  planner.py
  pi_prompt_compiler.py
  vet_interpreter.py
  review_decision.py
  revision_prompt.py
  learning_extractor.py
```

## Core signatures

### Workspace profiling

```python
class ProfileWorkspace(dspy.Signature):
    """Create durable project artifacts for a newly registered workspace."""

    product_description: str = dspy.InputField()
    repo_tree: str = dspy.InputField()
    key_files: str = dspy.InputField()

    architecture: str = dspy.OutputField()
    system_patterns: str = dspy.OutputField()
    testing: str = dspy.OutputField()
    design: str = dspy.OutputField()
    rules: str = dspy.OutputField()
    product: str = dspy.OutputField()
```

### Discovery

```python
class DiscoverTaskContext(dspy.Signature):
    """Build a task-specific implementation context package."""

    task: str = dspy.InputField()
    workspace_artifacts: str = dspy.InputField()
    repo_evidence: str = dspy.InputField()
    relevant_learnings: str = dspy.InputField()
    external_examples: str = dspy.InputField()

    task_type: str = dspy.OutputField(desc="feature | bugfix | refactor | optimization | docs | chore")
    scope: list[str] = dspy.OutputField()
    source_of_truth: str = dspy.OutputField()
    files_to_read: list[dict] = dspy.OutputField()
    files_to_modify: list[dict] = dspy.OutputField()
    constraints: list[str] = dspy.OutputField()
    risks: list[str] = dspy.OutputField()
    context_package_markdown: str = dspy.OutputField()
```

### Planning

```python
class CreateImplementationPlan(dspy.Signature):
    """Create an implementation-ready technical plan from a context package."""

    task: str = dspy.InputField()
    context_package: str = dspy.InputField()
    workspace_rules: str = dspy.InputField()
    relevant_learnings: str = dspy.InputField()

    summary: str = dspy.OutputField()
    current_state_analysis: str = dspy.OutputField()
    design: str = dspy.OutputField()
    file_by_file_impact: list[dict] = dspy.OutputField()
    implementation_order: list[str] = dspy.OutputField()
    acceptance_criteria: list[str] = dspy.OutputField()
    plan_markdown: str = dspy.OutputField()
```

### Pi prompt compilation

```python
class CompilePiPrompt(dspy.Signature):
    """Compile a strict execution prompt for Pi from approved context and plan artifacts."""

    task: str = dspy.InputField()
    context_package: str = dspy.InputField()
    implementation_plan: str = dspy.InputField()
    workspace_rules: str = dspy.InputField()
    relevant_learnings: str = dspy.InputField()

    execution_prompt: str = dspy.OutputField()
```

### Vet interpretation

```python
class InterpretVetOutput(dspy.Signature):
    """Convert raw Vet output into a structured blocking/non-blocking decision."""

    task: str = dspy.InputField()
    implementation_plan: str = dspy.InputField()
    git_diff: str = dspy.InputField()
    vet_output: str = dspy.InputField()

    passed: bool = dspy.OutputField()
    blockers: list[str] = dspy.OutputField()
    warnings: list[str] = dspy.OutputField()
    required_revisions: list[str] = dspy.OutputField()
    confidence: float = dspy.OutputField()
```

### Review decision

```python
class DecideReviewOutcome(dspy.Signature):
    """Decide whether the worktree is safe to merge."""

    task: str = dspy.InputField()
    implementation_plan: str = dspy.InputField()
    coder_summary: str = dspy.InputField()
    git_diff: str = dspy.InputField()
    test_output: str = dspy.InputField()
    vet_interpretation: str = dspy.InputField()
    workspace_artifacts: str = dspy.InputField()

    verdict: str = dspy.OutputField(desc="PASS | REVISE | FAIL")
    p1_critical: list[str] = dspy.OutputField()
    p2_major: list[str] = dspy.OutputField()
    p3_minor: list[str] = dspy.OutputField()
    revision_prompt: str = dspy.OutputField()
    review_markdown: str = dspy.OutputField()
```

### Learning extraction

```python
class ExtractLearning(dspy.Signature):
    """Extract reusable engineering learnings from a completed run."""

    run_record: str = dspy.InputField()
    final_diff: str = dspy.InputField()
    pr_feedback: str = dspy.InputField()
    review_history: str = dspy.InputField()

    learnings: list[dict] = dspy.OutputField()
    examples: list[dict] = dspy.OutputField()
    rejected_observations: list[str] = dspy.OutputField()
```

## Module structure

Each program should be wrapped as a DSPy module:

```python
class PlanningProgram(dspy.Module):
    def __init__(self):
        self.plan = dspy.ChainOfThought(CreateImplementationPlan)

    def forward(self, task, context_package, workspace_rules, relevant_learnings):
        return self.plan(
            task=task,
            context_package=context_package,
            workspace_rules=workspace_rules,
            relevant_learnings=relevant_learnings,
        )
```

Use `ChainOfThought` for reasoning-heavy tasks. Use direct prediction for extraction or formatting tasks when reasoning is not needed.

## Retrieval rules

The learning store should retrieve only relevant memory.

Inputs to retrieval:

- Task text
- Changed files
- Domain tags
- Artifact sections
- Historical failure mode tags

Avoid dumping all `.learning/` into every prompt. Memory pollution will make agents worse.

## Optimization loop

After enough runs, compile DSPy modules using examples.

```text
successful run artifacts
  → examples/*.jsonl
  → metrics score examples
  → DSPy optimizer compiles improved module
  → compiled module saved to .compound/compiled-dspy/
```

## Minimum viable DSPy rollout

Phase 1:

- Implement Signatures and Modules.
- Persist all inputs/outputs.
- No optimization yet.

Phase 2:

- Add metrics.
- Save examples.
- Score outputs offline.

Phase 3:

- Compile discovery/planning/review modules.
- Compare compiled vs uncompiled outputs.

Phase 4:

- Promote compiled modules only when evals improve.
