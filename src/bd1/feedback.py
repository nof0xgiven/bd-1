from __future__ import annotations

import re
from pathlib import Path

from bd1.artifacts import write_json
from bd1.models import FeedbackRecord

_FEEDBACK_FILE_RE = re.compile(r"feedback-(\d+)\.json")


def write_feedback(repo_path: str | Path, feedback: FeedbackRecord) -> Path:
    directory = Path(repo_path) / ".sessions" / feedback.run_id
    return write_feedback_in_dir(directory, feedback)


def write_feedback_in_dir(directory: str | Path, feedback: FeedbackRecord) -> Path:
    """Write feedback with a sequenced filename so repeat feedback never overwrites."""
    target_dir = Path(directory)
    numbers = [
        int(match.group(1))
        for path in target_dir.glob("feedback-*.json")
        if (match := _FEEDBACK_FILE_RE.fullmatch(path.name))
    ]
    next_number = max(numbers, default=0) + 1
    path = target_dir / f"feedback-{next_number:03d}.json"
    return write_json(path, feedback.to_dict(), redact=True)
