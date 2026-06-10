from __future__ import annotations

import fcntl
import json
import re
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bd1.artifacts import redact_data, write_json
from bd1.models import LearningRecord
from bd1.paths import slugify

ACTIVE_CONFIDENCE_THRESHOLD = 0.8
PENDING_CONFIDENCE_THRESHOLD = 0.5
LEARNING_STATUSES = ("active", "pending", "rejected", "superseded")
DEFAULT_LEARNING_CONFIDENCE = 0.5
_SAFE_EXAMPLE_KIND_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_LEARNING_RECORD_FIELDS = frozenset(item.name for item in fields(LearningRecord))


def learning_root(global_root: str | Path, workspace: str) -> Path:
    """Root of the global per-workspace learning store under BD1_HOME."""
    return Path(global_root) / "learning" / workspace


def status_for_confidence(confidence: float) -> str:
    if confidence >= ACTIVE_CONFIDENCE_THRESHOLD:
        return "active"
    if confidence >= PENDING_CONFIDENCE_THRESHOLD:
        return "pending"
    return "rejected"


def _normalize_learning(learning: LearningRecord) -> LearningRecord:
    if learning.status not in LEARNING_STATUSES:
        statuses = ", ".join(LEARNING_STATUSES)
        raise ValueError(
            f"Unsupported learning status {learning.status!r}; expected one of {statuses}"
        )
    if learning.status == "superseded":
        return learning
    return replace(learning, status=status_for_confidence(learning.confidence))


def learning_records_from_output(
    learnings: list[Any],
    *,
    run_id: str,
    task: str,
    event: str,
) -> list[LearningRecord]:
    """Parse raw learning dicts from the DSPy extractor into LearningRecords."""
    records: list[LearningRecord] = []
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for index, item in enumerate(learnings or [], start=1):
        if not isinstance(item, dict):
            continue
        rule = _coerce_str(item.get("rule"))
        if not rule.strip():
            continue
        learning_id = slugify(
            _coerce_str(item.get("id")) or f"{run_id}-{event}-{index}", max_length=120
        )
        records.append(
            LearningRecord(
                id=learning_id,
                created_at=created_at,
                status="pending",
                source_run_id=run_id,
                source_task=task,
                category=_coerce_str(item.get("category")),
                applies_when=_coerce_str(item.get("applies_when")),
                rule=rule,
                rationale=_coerce_str(item.get("rationale")),
                evidence=_coerce_evidence(item.get("evidence")),
                tags=_coerce_str_list(item.get("tags")),
                confidence=_coerce_confidence(item.get("confidence")),
                avoid_when=_coerce_str(item.get("avoid_when")),
                related_files=_coerce_str_list(item.get("related_files")),
            )
        )
    return records


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _coerce_evidence(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    return [
        {str(key): str(item_value) for key, item_value in item.items()}
        for item in value
        if isinstance(item, dict)
    ]


def _coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return DEFAULT_LEARNING_CONFIDENCE
    return min(max(confidence, 0.0), 1.0)


class LearningStore:
    """Learning store rooted at a directory (global per-workspace under BD1_HOME)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.learning_dir = self.root / "learnings"

    @classmethod
    def for_workspace(cls, global_root: str | Path, workspace: str) -> LearningStore:
        return cls(learning_root(global_root, workspace))

    def save_learning(self, learning: LearningRecord) -> Path:
        normalized = _normalize_learning(learning)
        path = self.learning_dir / f"{normalized.id}.json"
        return write_json(path, normalized.to_dict(), redact=True)

    def load_learnings(self) -> list[LearningRecord]:
        learnings, _ = self.load_learnings_with_warnings()
        return learnings

    def load_learnings_with_warnings(self) -> tuple[list[LearningRecord], list[str]]:
        if not self.learning_dir.exists():
            return [], []
        learnings: list[LearningRecord] = []
        skipped: list[str] = []
        for path in sorted(self.learning_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
                if not isinstance(data, dict):
                    raise ValueError("learning file is not a JSON object")
                payload = {
                    key: value for key, value in data.items() if key in _LEARNING_RECORD_FIELDS
                }
                learnings.append(LearningRecord.from_dict(payload))
            except (OSError, ValueError, TypeError, KeyError):
                skipped.append(path.name)
        return learnings, skipped

    def counts_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {status: 0 for status in LEARNING_STATUSES}
        for learning in self.load_learnings():
            counts[learning.status] = counts.get(learning.status, 0) + 1
        return counts

    def rebuild_index(self) -> Path:
        index: dict[str, Any] = {status: [] for status in LEARNING_STATUSES}
        index["learnings"] = []

        for learning in sorted(self.load_learnings(), key=lambda item: item.id):
            index.setdefault(learning.status, []).append(learning.id)
            index["learnings"].append(
                {
                    "id": learning.id,
                    "status": learning.status,
                    "confidence": learning.confidence,
                    "category": learning.category,
                    "tags": learning.tags,
                }
            )

        return write_json(self.root / "index.json", index, redact=True)

    def terminal_summary(self, example_store: ExampleStore | None = None) -> dict[str, Any]:
        learnings, skipped = self.load_learnings_with_warnings()
        counts: dict[str, int] = {status: 0 for status in LEARNING_STATUSES}
        for learning in learnings:
            counts[learning.status] = counts.get(learning.status, 0) + 1
        examples = (example_store or ExampleStore(self.root)).counts()
        return {
            "active": counts["active"],
            "pending": counts["pending"],
            "rejected": counts["rejected"],
            "superseded": counts["superseded"],
            "examples": examples,
            "corrupt_files": skipped,
        }

    def write_terminal_summary(self, example_store: ExampleStore | None = None) -> Path:
        return write_json(
            self.root / "terminal-summary.json",
            self.terminal_summary(example_store),
            redact=True,
        )


class ExampleStore:
    """Example JSONL store rooted at a directory (alongside the learnings/ subdir)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.examples_dir = self.root

    @classmethod
    def for_workspace(cls, global_root: str | Path, workspace: str) -> ExampleStore:
        return cls(learning_root(global_root, workspace))

    def append_example(self, kind: str, payload: dict[str, Any]) -> Path:
        if not _SAFE_EXAMPLE_KIND_RE.fullmatch(kind):
            raise ValueError(f"Unsupported example kind {kind!r}")

        path = self.examples_dir / f"{kind}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(redact_data(payload), sort_keys=True)
        with path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.write(line + "\n")
                handle.flush()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return path

    def count_examples(self, kind: str) -> int:
        path = self.examples_dir / f"{kind}.jsonl"
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    def counts(self) -> dict[str, int]:
        counts = {}
        if self.examples_dir.exists():
            for path in sorted(self.examples_dir.glob("*.jsonl")):
                counts[path.stem] = self.count_examples(path.stem)
        counts["total"] = sum(counts.values())
        return counts


def write_terminal_learning_summary(root: str | Path) -> Path:
    store = LearningStore(root)
    return store.write_terminal_summary(ExampleStore(root))
