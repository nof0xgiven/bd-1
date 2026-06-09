# Evaluation and Optimization

## Why metrics matter

A self-improving system cannot rely on vibes. Every stage must produce outputs that can be scored.

The goal is not just to store memory. The goal is to create examples that allow DSPy programs to improve.

## Evaluation targets

| Stage | Evaluated artifact | Example score criteria |
|---|---|---|
| Discovery | Context package | Correct files, proof lines, constraints, no irrelevant flooding. |
| Planning | Implementation plan | Specific file impact, clear sequence, no unsupported assumptions. |
| Execution prompt | Pi prompt | Complete context, strict boundaries, clear validation. |
| Vet interpretation | Structured Vet result | Correct blocker classification. |
| Review decision | PASS/REVISE/FAIL | Matches production-readiness outcome. |
| Learning extraction | Learning objects | Reusable, grounded, specific, correctly tagged. |

## Example metrics

### Discovery metric

```python
def discovery_metric(example, pred):
    score = 0
    if pred.source_of_truth:
        score += 0.20
    if pred.files_to_read and all("path" in f for f in pred.files_to_read):
        score += 0.20
    if pred.constraints:
        score += 0.15
    if pred.risks:
        score += 0.15
    if not contains_unproven_claims(pred.context_package_markdown):
        score += 0.20
    if not context_is_bloated(pred.context_package_markdown):
        score += 0.10
    return score
```

### Planning metric

```python
def planning_metric(example, pred):
    return weighted_score({
        "has_current_state": has_section(pred.plan_markdown, "Current-state analysis"),
        "has_file_impact": len(pred.file_by_file_impact) > 0,
        "has_order": len(pred.implementation_order) > 0,
        "no_full_code": not contains_copy_paste_implementation(pred.plan_markdown),
        "acceptance": len(pred.acceptance_criteria) > 0,
    })
```

### Review metric

```python
def review_metric(example, pred):
    if example.expected_verdict != pred.verdict:
        return 0
    return weighted_score({
        "critical_specific": findings_are_specific(pred.p1_critical),
        "major_specific": findings_are_specific(pred.p2_major),
        "minor_non_blocking": pred.verdict != "FAIL" or len(pred.p3_minor) >= 0,
        "revision_actionable": pred.verdict == "PASS" or is_actionable(pred.revision_prompt),
    })
```

## Promotion policy

A compiled DSPy program should only replace the current program if it beats the baseline on held-out examples.

Recommended rule:

```text
promote if:
  compiled_score >= baseline_score + 5%
  and no critical regressions on safety/production-readiness examples
```

## Dataset storage

```text
.examples/
  discovery.jsonl
  planning.jsonl
  pi_prompt.jsonl
  vet_interpretation.jsonl
  review_decision.jsonl
  learning.jsonl
```

Each example should include:

- input artifact references
- expected output
- scorer result
- source run ID
- creation timestamp
- whether it is train/dev/test

## Human feedback loop

When a human overrides a decision, capture it.

Examples:

- Human approved a review failure as acceptable.
- Human rejected a PASS because architecture was wrong.
- Human modified the plan before execution.
- Human removed a vague learning.

These overrides are high-value examples.
