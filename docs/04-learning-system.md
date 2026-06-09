# Learning System

## Purpose

The learning system converts completed engineering work into reusable operational knowledge.

It should capture:

- Mistakes
- Wins
- Review failures
- PR comments
- Vet failures
- CI failures
- Useful repo-specific patterns
- Bad assumptions that caused rework
- Validation commands that actually proved the work

## What counts as a learning

A learning must be:

1. Reusable beyond the current task.
2. Grounded in evidence from the run.
3. Specific enough to change future behavior.
4. Tagged so it can be retrieved selectively.
5. Scored for confidence.

Bad learning:

```text
Write better tests.
```

Good learning:

```text
When changing billing webhook behavior, validate against the real webhook handler path and persistence table. Unit-only service tests missed the integration boundary in run abc123.
```

## Learning lifecycle

```text
Merged PR
  → collect run artifacts
  → extract candidate learnings
  → reject vague/non-reusable observations
  → normalize into schema
  → save JSON
  → index by tags/files/domains
  → create DSPy examples
```

## Retrieval policy

Retrieve learnings by:

- Task semantic similarity
- File path overlap
- Domain tags
- Failure mode tags
- Architecture area
- Recency
- Confidence

Rank learnings with a blended score:

```text
score = relevance * confidence * freshness * usefulness
```

Where usefulness can be updated later when a learning appears in a successful run.

## Learning object fields

Required fields:

- id
- created_at
- source_run_id
- source_task
- category
- applies_when
- rule
- rationale
- evidence
- tags
- confidence

Optional fields:

- avoid_when
- related_files
- failure_mode
- validation_command
- supersedes
- superseded_by
- usage_count
- success_count

## Learning categories

```text
architecture_pattern
bug_prevention
testing_pattern
validation_command
integration_boundary
security_constraint
performance_constraint
domain_rule
workflow_improvement
prompt_improvement
```

## What not to store

Do not store:

- One-off facts with no future relevance.
- Entire transcripts.
- Low-confidence guesses.
- Generic advice.
- Sensitive secrets or credentials.
- Raw `.env` values.
- Large code dumps.

## Learning review

The system can auto-save high-confidence learnings, but should mark low-confidence candidates as pending review.

Suggested thresholds:

```text
confidence >= 0.80: active
0.50 <= confidence < 0.80: pending
confidence < 0.50: reject
```
