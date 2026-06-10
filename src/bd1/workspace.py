from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bd1.artifacts import ensure_global_dirs, ensure_workspace_dirs, write_text
from bd1.config import default_workspace_config, write_workspace_config
from bd1.errors import WorkspaceConfigError
from bd1.git import default_branch as detect_default_branch
from bd1.git import ensure_clean_repo, ensure_git_repo
from bd1.models import WorkspaceConfig
from bd1.paths import global_state_dir
from bd1.registry import WorkspaceRegistry

NO_EVIDENCE = "No evidence found in scanned files."

WORKSPACE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

PROFILE_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", "pyproject.toml", "package.json")
PROFILE_ARTIFACTS = {
    "architecture": "architecture.md",
    "system_patterns": "system-patterns.md",
    "testing": "testing.md",
    "design": "design.md",
    "rules": "rules.md",
    "product": "product.md",
}


@dataclass(frozen=True)
class WorkspaceAddResult:
    config: WorkspaceConfig
    guidance: str


@dataclass(frozen=True)
class SourceEvidence:
    relative_path: str
    text: str


def add_workspace(
    name: str,
    repo: str | Path,
    product: str,
    *,
    setup_script: str = "",
    default_branch: str = "",
    registry: WorkspaceRegistry | None = None,
) -> WorkspaceAddResult:
    if not WORKSPACE_NAME_RE.fullmatch(name):
        raise WorkspaceConfigError(
            f"Invalid workspace name: {name!r}. Use letters, digits, '-' or '_', "
            "starting with a letter or digit."
        )
    repo_path = Path(repo).expanduser().resolve()
    ensure_git_repo(repo_path)
    ensure_clean_repo(repo_path)

    active_registry = registry or WorkspaceRegistry(global_state_dir())
    ensure_global_dirs(active_registry.state_dir)
    ensure_workspace_dirs(repo_path)

    config = default_workspace_config(
        name=name,
        repo_path=str(repo_path),
        product_description=product,
        setup_script=setup_script,
        default_branch=default_branch or detect_default_branch(repo_path),
    )
    write_workspace_config(repo_path, config)
    profile_workspace(config)
    active_registry.add(config)

    guidance = (
        "Review and commit generated bd-1 workspace files before task runs: "
        ".bd-1.toml and .artifacts/. "
        "Learnings and examples are stored globally under BD1_HOME."
    )
    return WorkspaceAddResult(config=config, guidance=guidance)


def profile_workspace(config: WorkspaceConfig) -> list[Path]:
    repo_path = Path(config.repo_path).expanduser().resolve()
    ensure_workspace_dirs(repo_path)
    sources = _read_profile_sources(repo_path)

    profile = {
        "architecture": _render_evidence(
            _matching_sources(
                sources,
                path_terms=("architecture",),
                content_terms=("architecture", "boundary", "service", "pipeline"),
            )
        ),
        "system_patterns": _render_evidence(
            _matching_sources(
                sources,
                path_terms=("pattern", "pyproject.toml", "package.json"),
                content_terms=("pattern", "convention", "workflow"),
            )
        ),
        "testing": _render_evidence(
            _matching_sources(
                sources,
                path_terms=("test", "qa"),
                content_terms=("test", "pytest", "ruff", "coverage", "qa"),
            )
        ),
        "design": _render_evidence(
            _matching_sources(
                sources,
                path_terms=("design", "ux", "ui"),
                content_terms=("design", "interface", "visual", "ux", "ui"),
            )
        ),
        "rules": _render_evidence(
            _matching_sources(
                sources,
                path_terms=("agents.md", "claude.md", "rules", "instructions"),
                content_terms=("always", "must", "never", "instruction"),
            )
        ),
        "product": _render_evidence(
            [
                SourceEvidence("workspace product description", config.product_description),
                *_matching_sources(
                    sources,
                    path_terms=("readme.md", "product", "prd"),
                    content_terms=("product",),
                ),
            ]
        ),
    }

    written = []
    for key, filename in PROFILE_ARTIFACTS.items():
        written.append(write_text(repo_path / ".artifacts" / filename, profile[key]))
    return written


def _read_profile_sources(repo: Path) -> list[SourceEvidence]:
    sources = []
    for relative in PROFILE_FILES:
        path = repo / relative
        if path.is_file():
            sources.append(SourceEvidence(relative, _read_text(path)))

    docs = repo / "docs"
    if docs.is_dir():
        for path in sorted(item for item in docs.rglob("*") if item.is_file()):
            sources.append(SourceEvidence(path.relative_to(repo).as_posix(), _read_text(path)))

    return [source for source in sources if source.text.strip()]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _matching_sources(
    sources: list[SourceEvidence],
    *,
    path_terms: tuple[str, ...],
    content_terms: tuple[str, ...],
) -> list[SourceEvidence]:
    matches = []
    for source in sources:
        relative_path = source.relative_path.lower()
        content = source.text.lower()
        if any(term in relative_path for term in path_terms) or any(
            term in content for term in content_terms
        ):
            matches.append(source)
    return matches


def _render_evidence(sources: list[SourceEvidence]) -> str:
    evidence = [source for source in sources if source.text.strip()]
    if not evidence:
        return NO_EVIDENCE

    sections = []
    for source in evidence:
        sections.append(f"## {source.relative_path}\n\n{source.text.strip()}")
    return "\n\n".join(sections) + "\n"
