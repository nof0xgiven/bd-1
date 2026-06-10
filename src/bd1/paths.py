from __future__ import annotations

import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path


def global_state_dir() -> Path:
    # Resolve so a relative BD1_HOME cannot leak relative paths into every
    # derived location (archives, learning stores, run pointers).
    return Path(os.environ.get("BD1_HOME", Path.home() / ".bd-1")).expanduser().resolve()


def slugify(value: str, max_length: int = 60) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:max_length].strip("-") or "task"


def make_run_id(task: str, now: str | None = None, *, suffix: str | None = None) -> str:
    moment = datetime.now(UTC) if now is None else datetime.fromisoformat(now)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    stamp = moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    token = secrets.token_hex(2) if suffix is None else suffix
    return f"run-{stamp}-{slugify(task)}-{token}"
