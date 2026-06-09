from __future__ import annotations

from pathlib import Path

from bd1.artifacts import write_json
from bd1.models import FeedbackRecord


def write_feedback(repo_path: str | Path, feedback: FeedbackRecord) -> Path:
    path = Path(repo_path) / ".sessions" / feedback.run_id / "feedback.json"
    return write_json(path, feedback.to_dict(), redact=True)
