from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from bd1.evidence import collect_evidence
from bd1.learning import ExampleStore, LearningStore, learning_records_from_output
from bd1.models import RunRecord, RunState, WorkspaceConfig
from bd1.run_store import RunStore, now_iso

GH_TIMEOUT_SECONDS = 120

ARCHIVED_CONTEXT_FILES = (
    "discovery-context.md",
    "plan.md",
    "completed.md",
    "vet-output.json",
    "pi-session.jsonl",
)
MAX_ARCHIVED_CONTEXT_BYTES = 32_000


@dataclass(frozen=True)
class SyncOutcome:
    checked: int = 0
    learned: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)


def eligible(record: RunRecord) -> bool:
    return (
        record.state is RunState.COMPLETE
        and record.pr_number is not None
        and not record.merge_synced_at
    )


def sync_runs(
    *,
    run_store: RunStore,
    records: list[RunRecord],
    config: WorkspaceConfig,
    reasoning: Any,
    runner: Callable[..., Any],
    global_root: str | Path,
) -> SyncOutcome:
    learned: list[str] = []
    skipped: dict[str, str] = {}
    candidates = [record for record in records if eligible(record)]
    for record in candidates:
        try:
            result = runner(
                ["gh", "pr", "view", str(record.pr_number), "--json", "state,mergedAt"],
                cwd=config.repo_path,
                timeout=GH_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # CommandStartError et al: skip, don't abort the sweep
            skipped[record.run_id] = f"gh pr view failed to start: {exc}"
            continue
        if result.exit_code != 0:
            skipped[record.run_id] = f"gh pr view failed: {result.stderr.strip()[:200]}"
            continue
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            skipped[record.run_id] = "gh pr view returned invalid JSON"
            continue
        state = str(payload.get("state", "")).upper()
        if state != "MERGED":
            skipped[record.run_id] = f"not merged ({state or 'UNKNOWN'})"
            continue
        _learn_from_merge(
            run_store=run_store,
            record=record,
            reasoning=reasoning,
            global_root=global_root,
        )
        learned.append(record.run_id)
    return SyncOutcome(checked=len(candidates), learned=learned, skipped=skipped)


def _learn_from_merge(
    *,
    run_store: RunStore,
    record: RunRecord,
    reasoning: Any,
    global_root: str | Path,
) -> None:
    learning_store = LearningStore.for_workspace(global_root, record.workspace)
    example_store = ExampleStore.for_workspace(global_root, record.workspace)
    final_diff, review, pr_feedback = _learning_inputs(run_store, record)

    # Evidence must describe THE RUN, not the repo's later state: when the
    # worktree is gone, root the evidence at the archive and inline the
    # archived run artifacts as extra context.
    worktree = Path(record.worktree)
    archive = run_store.archive_dir(record.run_id)
    evidence_root = worktree if worktree.is_dir() else archive
    evidence = collect_evidence(evidence_root, task=record.task, learning_store=learning_store)
    evidence = replace(evidence, extra_context=_archived_context(archive))
    output = reasoning.learn(
        evidence,
        review_markdown=f"pr merged\n\n{review}",
        final_diff=final_diff,
        pr_feedback=pr_feedback,
    )
    for learning in learning_records_from_output(
        output.learnings, run_id=record.run_id, task=record.task, event="pr-merged"
    ):
        learning_store.save_learning(learning)
    example_store.append_example(
        "learning",
        {"run_id": record.run_id, "event": "pr merged", "markdown": output.markdown},
    )
    updated = replace(record, merge_synced_at=now_iso())
    if worktree.is_dir():
        run_store.write(worktree, updated)
    else:
        run_store.write_archived(updated)


def _archived_context(archive: Path) -> str:
    """Inline archived run artifacts (sessions, plans, discovery) for learning."""
    sections: list[str] = []
    used = 0
    for name in ARCHIVED_CONTEXT_FILES:
        path = archive / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        remaining = MAX_ARCHIVED_CONTEXT_BYTES - used
        if remaining <= 0:
            sections.append("... archived context truncated")
            break
        if len(text) > remaining:
            text = text[:remaining] + "\n... truncated"
        used += len(text)
        sections.append(f"## archived:{name}\n\n{text}")
    return "\n\n".join(sections)


def _learning_inputs(run_store: RunStore, record: RunRecord) -> tuple[str, str, str]:
    archive = run_store.archive_dir(record.run_id)

    def read_first(*candidates: Path) -> str:
        for candidate in candidates:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8", errors="replace")
        return ""

    final_attempt = record.attempts[-1] if record.attempts else None
    diff = read_first(
        *([Path(final_attempt.git_diff_path)] if final_attempt else []),
        archive / "final-diff.patch",
    )
    review = read_first(
        *([Path(final_attempt.review_path)] if final_attempt else []),
        archive / "review.md",
    )
    feedback_paths = [Path(path) for path in record.pr_feedback_paths]
    archived_feedback = sorted(archive.glob("pr-feedback-*.md"))
    chosen = feedback_paths if any(path.is_file() for path in feedback_paths) else archived_feedback
    pr_feedback = "\n\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in chosen if path.is_file()
    )
    return diff, review, pr_feedback
