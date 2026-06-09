from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXCLUDED_TREE_DIRS = frozenset({".git", ".sessions", ".venv", "node_modules", "__pycache__"})


@dataclass(frozen=True)
class EvidencePackage:
    task: str
    repo_path: str
    repo_tree: str
    workspace_artifacts: str
    relevant_learnings: str
    extra_context: str = ""


def collect_evidence(repo: str | Path, *, task: str, extra_context: str = "") -> EvidencePackage:
    root = Path(repo)
    return EvidencePackage(
        task=task,
        repo_path=str(root),
        repo_tree=_collect_repo_tree(root),
        workspace_artifacts=_collect_workspace_artifacts(root),
        relevant_learnings=_collect_relevant_learnings(root),
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


def _collect_relevant_learnings(root: Path) -> str:
    learning_roots = [
        root / ".learning" / "learnings",
    ]
    sections: list[str] = []
    seen: set[Path] = set()
    for learning_root in learning_roots:
        for path in _iter_files_with_suffix(learning_root, ".json"):
            if path in seen:
                continue
            seen.add(path)
            sections.append(f"# {_relative_path(path, root)}\n{_read_json_for_context(path)}")
    for path in _iter_files_with_suffix(root / ".artifacts" / "learning", ".md"):
        if path in seen:
            continue
        seen.add(path)
        sections.append(f"# {_relative_path(path, root)}\n{_read_text(path)}")
    return "\n\n".join(sections)


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


def _read_json_for_context(path: Path) -> str:
    text = _read_text(path)
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(data, indent=2, sort_keys=True)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
