from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from bd1.learning import LearningStore

EXCLUDED_TREE_DIRS = frozenset({".git", ".sessions", ".venv", "node_modules", "__pycache__"})
INCLUDED_LEARNING_STATUSES = frozenset({"active", "pending"})
MAX_RELEVANT_LEARNINGS_BYTES = 64 * 1024


@dataclass(frozen=True)
class EvidencePackage:
    task: str
    repo_path: str
    repo_tree: str
    workspace_artifacts: str
    relevant_learnings: str
    extra_context: str = ""


def collect_evidence(
    repo: str | Path,
    *,
    task: str,
    extra_context: str = "",
    learning_store: LearningStore | None = None,
) -> EvidencePackage:
    root = Path(repo)
    return EvidencePackage(
        task=task,
        repo_path=str(root),
        repo_tree=_collect_repo_tree(root),
        workspace_artifacts=_collect_workspace_artifacts(root),
        relevant_learnings=_collect_relevant_learnings(root, learning_store),
        extra_context=extra_context,
    )


def _collect_repo_tree(root: Path) -> str:
    return "\n".join(_relative_path(path, root) for path in _iter_repo_files(root))


def _iter_repo_files(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(directory for directory in dirs if directory not in EXCLUDED_TREE_DIRS)
        current_path = Path(current)
        for filename in sorted(files):
            path = current_path / filename
            relative_parts = path.relative_to(root).parts
            if any(part in EXCLUDED_TREE_DIRS for part in relative_parts[:-1]):
                continue
            yield path


def _collect_workspace_artifacts(root: Path) -> str:
    artifacts_root = root / ".artifacts"
    paths = sorted(artifacts_root.glob("*.md")) if artifacts_root.exists() else []
    paths.extend(_iter_files_with_suffix(artifacts_root / "context", ".md"))
    return _join_file_sections(paths, root)


def _collect_relevant_learnings(root: Path, learning_store: LearningStore | None) -> str:
    sections: list[str] = []
    if learning_store is not None:
        for learning in learning_store.load_learnings():
            if learning.status not in INCLUDED_LEARNING_STATUSES:
                continue
            payload = json.dumps(learning.to_dict(), indent=2, sort_keys=True)
            sections.append(f"# learning:{learning.id} (status={learning.status})\n{payload}")
    for path in _iter_files_with_suffix(root / ".artifacts" / "learning", ".md"):
        sections.append(f"# {_relative_path(path, root)}\n{_read_text(path)}")
    return _cap_sections(sections, MAX_RELEVANT_LEARNINGS_BYTES)


def _cap_sections(sections: list[str], max_bytes: int) -> str:
    included: list[str] = []
    total = 0
    omitted = 0
    for section in sections:
        size = len(section.encode("utf-8")) + 2
        if total + size > max_bytes:
            omitted += 1
            continue
        included.append(section)
        total += size
    if omitted:
        included.append(
            f"[truncated: relevant learnings exceeded {max_bytes} bytes; "
            f"{omitted} section(s) omitted]"
        )
    return "\n\n".join(included)


def _iter_files_with_suffix(root: Path, suffix: str) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob(f"*{suffix}")
        if path.is_file()
        and not any(part in EXCLUDED_TREE_DIRS for part in path.relative_to(root).parts[:-1])
    )


def _join_file_sections(paths: list[Path], root: Path) -> str:
    sections = [f"# {_relative_path(path, root)}\n{_read_text(path)}" for path in paths]
    return "\n\n".join(sections)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
