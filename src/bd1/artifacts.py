from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

WORKSPACE_DIRS = [
    ".artifacts/context",
    ".artifacts/plans",
    ".artifacts/completed",
    ".artifacts/vet",
    ".artifacts/reviews",
    ".artifacts/pr",
    ".artifacts/blockers",
    ".artifacts/learning",
    ".sessions",
]

GLOBAL_DIRS = ["runs", "compiled-dspy", "logs", "worktrees"]

_KEY_VALUE_QUOTED_RE = re.compile(
    r"(?i)(?P<prefix>\b(?P<key>[a-z0-9_-]+)\b[\"']?\s*[:=]\s*)"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)"
)
_KEY_VALUE_UNQUOTED_RE = re.compile(
    r"(?i)(?P<prefix>\b(?P<key>[a-z0-9_-]+)\b[\"']?\s*[:=]\s*)"
    r"(?![\"'])(?P<value>[^\s,}\]]+)"
)
# Redacts everything after "authorization:" (scheme and credential), in both
# header form (Authorization: Basic abc) and quoted form ("Authorization": "token abc").
_AUTHORIZATION_RE = re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)([^\r\n\"']+)")
# Standalone credential shapes that should never survive redaction.
_TOKEN_SHAPES_RE = re.compile(
    r"\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bghp_[A-Za-z0-9]{20,}"
    r"|\bsk-[A-Za-z0-9_-]{20,}"
    r"|\bAKIA[A-Z0-9]{16}\b"
    r"|\bxox[a-z]-[A-Za-z0-9-]{10,}"
)
_DATABASE_URL_RE = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss)"
    r"://[^\s\"']+"
)
_SECRET_TERMS = {"authorization", "password", "pass", "pwd", "secret", "token"}
_SECRET_COMPACT_SUFFIXES = (
    "apikey",
    "token",
    "secret",
    "password",
    "privatekey",
    "accesskey",
    "accesskeyid",
    "accesstoken",
    "refreshtoken",
    "clientsecret",
    "databaseurl",
    "dburl",
)


def _normalize_key(key: str) -> list[str]:
    split_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", split_camel).strip("_").lower()
    return [part for part in normalized.split("_") if part]


def _is_secret_key(key: str) -> bool:
    parts = _normalize_key(key)
    if not parts:
        return False

    compact = "".join(parts)
    if compact in {"authorization", "pass", "pwd"}:
        return True
    if any(part in _SECRET_TERMS for part in parts):
        return True
    return compact.endswith(_SECRET_COMPACT_SUFFIXES)


def _redact_key_value(match: re.Match[str]) -> str:
    if not _is_secret_key(match.group("key")):
        return match.group(0)

    quote = match.groupdict().get("quote")
    if quote:
        return f"{match.group('prefix')}{quote}[REDACTED]{quote}"
    return f"{match.group('prefix')}[REDACTED]"


def redact_data(data: Any) -> Any:
    return _redact_json_data(data)


def _redact_json_data(data: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_secret_key(key):
        return "[REDACTED]"
    if isinstance(data, dict):
        return {
            str(item_key): _redact_json_data(value, key=str(item_key))
            for item_key, value in data.items()
        }
    if isinstance(data, list):
        return [_redact_json_data(item) for item in data]
    if isinstance(data, str):
        return redact_text(data)
    return data


def ensure_workspace_dirs(repo: str | Path) -> None:
    root = Path(repo)
    for relative in WORKSPACE_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)


def ensure_global_dirs(root: str | Path) -> None:
    root_path = Path(root)
    for relative in GLOBAL_DIRS:
        (root_path / relative).mkdir(parents=True, exist_ok=True)


def redact_text(text: str) -> str:
    redacted = _DATABASE_URL_RE.sub("[REDACTED]", text)
    redacted = _TOKEN_SHAPES_RE.sub("[REDACTED]", redacted)
    redacted = _AUTHORIZATION_RE.sub(r"\1[REDACTED]", redacted)
    redacted = _KEY_VALUE_QUOTED_RE.sub(_redact_key_value, redacted)
    return _KEY_VALUE_UNQUOTED_RE.sub(_redact_key_value, redacted)


def write_text(path: str | Path, text: str, *, redact: bool = True) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = redact_text(text) if redact else text
    descriptor, temp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return target


def write_json(path: str | Path, data: Any, *, redact: bool = False) -> Path:
    payload = _redact_json_data(data) if redact else data
    text = json.dumps(payload, indent=2, sort_keys=True)
    return write_text(path, text + "\n", redact=False)
