# Storage Layout

## Workspace storage

Each workspace repository should contain durable local intelligence:

```text
workspace-root/
  .artifacts/
    architecture.md
    system-patterns.md
    testing.md
    design.md
    rules.md
    product.md
    context/
      <task-name>.md
    plans/
      <task-name>.md
    completed/
      <task-name>.md
    reviews/
      <task-name>-01-pass.md
      <task-name>-01-fail.md
    pr/
      <task-name>-01.md
      <task-name>-01-complete.md
  .learning/
    learnings/
      <learning-id>.json
    index.json
  .examples/
    discovery.jsonl
    planning.jsonl
    review.jsonl
    learning.jsonl
  .sessions/
    <run-id>/
      run-record.json
      pi-session.txt
      vet-output.txt
      git-diff.patch
      test-output.txt
```

## Global storage

The orchestrator can maintain global state outside repos:

```text
.compound/
  workspaces.json
  runs/
  compiled-dspy/
  logs/
```

## Naming conventions

Task names should be slugified:

```text
Add billing webhook retry → add-billing-webhook-retry
```

Run IDs should be globally unique:

```text
run_2026_06_09_001_add_billing_webhook_retry
```

## Artifact immutability

Task artifacts should be append-only where possible.

If a plan changes due to revision, write:

```text
.artifacts/plans/<task-name>-v1.md
.artifacts/plans/<task-name>-v2.md
```

Do not overwrite old artifacts unless explicitly working on durable workspace docs.

PR lifecycle artifacts always use the lowercase runtime directory `.artifacts/pr/`. Feedback artifacts capture actionable CI, CodeRabbit, or human review items. Complete artifacts mark that PR checks and review feedback are clear for the monitored PR.

## Secrets policy

Never persist:

- Raw `.env` contents
- API keys
- tokens
- database passwords
- production credentials
- private customer data unless explicitly allowed by workspace policy

If a session transcript contains secrets, redact before saving learning artifacts.
