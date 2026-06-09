from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path


def global_state_dir() -> Path:
    return Path(os.environ.get("BD1_HOME", Path.home() / ".bd-1")).expanduser()


def slugify(value: str, max_length: int = 60) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:max_length].strip("-") or "task"


def make_run_id(task: str, now: str | None = None) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if now is not None:
        stamp = now.replace("-", "").replace(":", "").replace("+00:00", "Z")
    return f"run-{stamp}-{slugify(task)}"
