from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from bd1.artifacts import redact_data, write_json
from bd1.models import LearningRecord

ACTIVE_CONFIDENCE_THRESHOLD = 0.8
PENDING_CONFIDENCE_THRESHOLD = 0.5
LEARNING_STATUSES = ("active", "pending", "rejected", "superseded")
_SAFE_EXAMPLE_KIND_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


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


class LearningStore:
    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path)
        self.learning_dir = self.repo_path / ".learning" / "learnings"

    def save_learning(self, learning: LearningRecord) -> Path:
        normalized = _normalize_learning(learning)
        path = self.learning_dir / f"{normalized.id}.json"
        return write_json(path, normalized.to_dict(), redact=True)

    def load_learnings(self) -> list[LearningRecord]:
        if not self.learning_dir.exists():
            return []
        learnings = []
        for path in sorted(self.learning_dir.glob("*.json")):
            learnings.append(LearningRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return learnings

    def counts_by_status(self) -> dict[str, int]:
        counts = dict.fromkeys(LEARNING_STATUSES, 0)
        for learning in self.load_learnings():
            if learning.status not in counts:
                raise ValueError(
                    f"Unsupported learning status {learning.status!r} in {learning.id}"
                )
            counts[learning.status] += 1
        return counts

    def rebuild_index(self) -> Path:
        index: dict[str, Any] = {status: [] for status in LEARNING_STATUSES}
        index["learnings"] = []

        for learning in sorted(self.load_learnings(), key=lambda item: item.id):
            if learning.status not in LEARNING_STATUSES:
                raise ValueError(
                    f"Unsupported learning status {learning.status!r} in {learning.id}"
                )
            index[learning.status].append(learning.id)
            index["learnings"].append(
                {
                    "id": learning.id,
                    "status": learning.status,
                    "confidence": learning.confidence,
                    "category": learning.category,
                    "tags": learning.tags,
                }
            )

        return write_json(self.repo_path / ".learning" / "index.json", index, redact=True)

    def terminal_summary(self, example_store: ExampleStore | None = None) -> dict[str, Any]:
        counts = self.counts_by_status()
        examples = (example_store or ExampleStore(self.repo_path)).counts()
        return {
            "active": counts["active"],
            "pending": counts["pending"],
            "rejected": counts["rejected"],
            "superseded": counts["superseded"],
            "examples": examples,
        }

    def write_terminal_summary(self, example_store: ExampleStore | None = None) -> Path:
        return write_json(
            self.repo_path / ".artifacts" / "learning" / "terminal-summary.json",
            self.terminal_summary(example_store),
            redact=True,
        )


class ExampleStore:
    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path)
        self.examples_dir = self.repo_path / ".examples"

    def append_example(self, kind: str, payload: dict[str, Any]) -> Path:
        if not _SAFE_EXAMPLE_KIND_RE.fullmatch(kind):
            raise ValueError(f"Unsupported example kind {kind!r}")

        path = self.examples_dir / f"{kind}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(redact_data(payload), sort_keys=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
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


def write_terminal_learning_summary(repo_path: str | Path) -> Path:
    store = LearningStore(repo_path)
    return store.write_terminal_summary(ExampleStore(repo_path))
