from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bd1.artifacts import ensure_global_dirs, ensure_workspace_dirs, write_text
from bd1.config import default_workspace_config, write_workspace_config
from bd1.errors import ReasoningOutputError, WorkspaceConfigError
from bd1.git import default_branch as detect_default_branch
from bd1.git import ensure_clean_repo, ensure_git_repo
from bd1.models import WorkspaceConfig
from bd1.paths import global_state_dir
from bd1.registry import WorkspaceRegistry
from bd1.repo_tools import RepoTools

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
PROFILE_WARNING_FILE = "profile-warning.md"
PROFILE_DEGRADED_NOTICE = (
    "agentic profiling failed, keyword fallback used — see .artifacts/profile-warning.md"
)
# Evidence fed to the LM: these tools cap prompt size and skip binary blobs.
PROFILE_TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".mdx",
        ".markdown",
        ".adoc",
        ".rst",
        ".txt",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".py",
        ".cfg",
        ".ini",
    }
)
PROFILE_EXCERPT_LIMIT = 4000
PROFILE_EXCERPT_BUDGET = 150_000


@dataclass(frozen=True)
class WorkspaceAddResult:
    config: WorkspaceConfig
    guidance: str
    profile_warning: str = ""


@dataclass(frozen=True)
class ProfileResult:
    written: tuple[Path, ...]
    warning: str = ""


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
    reasoning_factory: Callable[[WorkspaceConfig], object] | None = None,
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
    # The factory takes the freshly built config: it does not exist before here.
    profile_result = profile_workspace(
        config, reasoning=reasoning_factory(config) if reasoning_factory else None
    )
    active_registry.add(config)

    guidance = (
        "Review and commit generated bd-1 workspace files before task runs: "
        ".bd-1.toml and .artifacts/. "
        "Learnings and examples are stored globally under BD1_HOME."
    )
    if profile_result.warning:
        guidance = f"{guidance} Warning: {profile_result.warning}"
    return WorkspaceAddResult(
        config=config, guidance=guidance, profile_warning=profile_result.warning
    )


def profile_workspace(config: WorkspaceConfig, reasoning=None) -> ProfileResult:
    repo_path = Path(config.repo_path).expanduser().resolve()
    ensure_workspace_dirs(repo_path)
    sources = _read_profile_sources(repo_path)
    warning_path = repo_path / ".artifacts" / PROFILE_WARNING_FILE

    profile: dict[str, str] | None = None
    warning = ""
    if reasoning is not None:
        try:
            profile = _agentic_profile(repo_path, config, sources, reasoning)
            warning_path.unlink(missing_ok=True)
        except Exception as exc:
            # A configured-but-unusable LM must not abort `workspace add`;
            # the keyword heuristic is the documented fallback.
            write_text(
                warning_path,
                f"Agentic profiling failed; keyword fallback used.\n\n{exc}\n",
            )
            warning = PROFILE_DEGRADED_NOTICE
    if profile is None:
        profile = _keyword_profile(config, sources)

    written = tuple(
        write_text(repo_path / ".artifacts" / filename, profile[key])
        for key, filename in PROFILE_ARTIFACTS.items()
    )
    return ProfileResult(written=written, warning=warning)


def _agentic_profile(
    repo_path: Path,
    config: WorkspaceConfig,
    sources: list[SourceEvidence],
    reasoning,
) -> dict[str, str]:
    tree = RepoTools(repo_path).list_tree()
    sections: list[str] = []
    used = 0
    omitted = 0
    for index, source in enumerate(sources):
        section = f"## {source.relative_path}\n\n{source.text[:PROFILE_EXCERPT_LIMIT]}"
        if used + len(section) > PROFILE_EXCERPT_BUDGET:
            omitted = len(sources) - index
            break
        sections.append(section)
        used += len(section)
    if omitted:
        sections.append(f"... truncated: {omitted} more sources omitted")
    excerpts = "\n\n".join(sections)
    output = reasoning.profile(
        repo_evidence=f"# File tree\n{tree}\n\n# Key files\n{excerpts}",
        product_description=config.product_description,
    )
    profile = dict(output.artifacts)
    missing = set(PROFILE_ARTIFACTS) - set(profile)
    if missing:
        raise ReasoningOutputError(f"Profile missing artifact(s): {', '.join(sorted(missing))}")
    return profile


def _keyword_profile(config: WorkspaceConfig, sources: list[SourceEvidence]) -> dict[str, str]:
    return {
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


def _read_profile_sources(repo: Path) -> list[SourceEvidence]:
    sources = []
    for relative in PROFILE_FILES:
        path = repo / relative
        if path.is_file():
            sources.append(SourceEvidence(relative, _read_text(path)))

    docs = repo / "docs"
    if docs.is_dir():
        for path in sorted(item for item in docs.rglob("*") if item.is_file()):
            if path.suffix.lower() not in PROFILE_TEXT_SUFFIXES:
                continue  # binary/unknown formats become mojibake, not evidence
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
