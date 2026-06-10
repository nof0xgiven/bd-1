import subprocess

import pytest

from bd1.config import default_workspace_config
from bd1.dspy_programs import ProfileOutput
from bd1.errors import DirtyRepositoryError, WorkspaceConfigError
from bd1.registry import WorkspaceRegistry
from bd1.workspace import add_workspace, profile_workspace


@pytest.mark.parametrize("name", ["", "-demo", "demo/evil", "demo space", "../demo"])
def test_add_workspace_rejects_unsafe_names(tmp_path, init_git_repo, name):
    repo = init_git_repo(tmp_path / "repo")

    with pytest.raises(WorkspaceConfigError) as exc:
        add_workspace(name, repo, "Demo", registry=WorkspaceRegistry(tmp_path / "state"))

    assert "Invalid workspace name" in str(exc.value)


def test_add_workspace_fails_on_dirty_repo(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(DirtyRepositoryError):
        add_workspace("demo", repo, "Demo", registry=WorkspaceRegistry(tmp_path / "state"))


def test_add_workspace_writes_config_dirs_and_guidance(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    registry = WorkspaceRegistry(tmp_path / "state")

    result = add_workspace("demo", repo, "Demo product", registry=registry)

    assert result.config.name == "demo"
    assert (repo / ".bd-1.toml").exists()
    assert (repo / ".artifacts" / "context").is_dir()
    assert (repo / ".artifacts" / "product.md").exists()
    assert "Review and commit generated bd-1 workspace files" in result.guidance
    assert ".sessions/" not in result.guidance
    assert registry.get("demo").repo_path == str(repo.resolve())


def test_profile_uses_repo_evidence(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    (repo / "AGENTS.md").write_text("Always run tests.\n", encoding="utf-8")
    subprocess.run(["git", "add", "AGENTS.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add agents"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    result = add_workspace(
        "demo", repo, "Demo product", registry=WorkspaceRegistry(tmp_path / "state")
    )

    profile_workspace(result.config)

    assert "Always run tests." in (repo / ".artifacts" / "rules.md").read_text(encoding="utf-8")
    assert "Demo product" in (repo / ".artifacts" / "product.md").read_text(encoding="utf-8")


def test_profile_reads_docs_when_present(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    docs = repo / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("Use a pipeline architecture.\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/architecture.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add architecture docs"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    add_workspace("demo", repo, "Demo product", registry=WorkspaceRegistry(tmp_path / "state"))

    assert "Use a pipeline architecture." in (repo / ".artifacts" / "architecture.md").read_text(
        encoding="utf-8"
    )
    assert "docs/architecture.md" in (repo / ".artifacts" / "architecture.md").read_text(
        encoding="utf-8"
    )


def test_profile_unknown_sections_use_exact_fallback(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    result = add_workspace(
        "demo", repo, "Demo product", registry=WorkspaceRegistry(tmp_path / "state")
    )

    profile_workspace(result.config)

    assert (repo / ".artifacts" / "design.md").read_text(
        encoding="utf-8"
    ).strip() == "No evidence found in scanned files."


class _RecordingProfiler:
    def __init__(self):
        self.calls = []

    def profile(self, *, repo_evidence, product_description):
        self.calls.append((repo_evidence, product_description))
        artifacts = {
            key: f"agentic {key}"
            for key in ("architecture", "system_patterns", "testing", "design", "rules", "product")
        }
        return ProfileOutput(artifacts=artifacts)


def test_profile_workspace_prefers_reasoning_when_provided(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    config = default_workspace_config(
        name="demo", repo_path=str(repo), product_description="demo product"
    )
    profiler = _RecordingProfiler()

    result = profile_workspace(config, reasoning=profiler)

    assert (repo / ".artifacts" / "architecture.md").read_text(
        encoding="utf-8"
    ) == "agentic architecture"
    assert len(result.written) == 6
    assert result.warning == ""
    assert profiler.calls and "demo product" in profiler.calls[0][1]


def test_profile_workspace_keyword_fallback_without_reasoning(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    config = default_workspace_config(
        name="demo", repo_path=str(repo), product_description="demo product"
    )

    profile_workspace(config)

    assert (repo / ".artifacts" / "product.md").exists()


def test_profile_workspace_falls_back_when_reasoning_fails(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    config = default_workspace_config(
        name="demo", repo_path=str(repo), product_description="demo product"
    )

    class _Exploding:
        def profile(self, **kwargs):
            raise RuntimeError("LM down")

    result = profile_workspace(config, reasoning=_Exploding())

    assert len(result.written) == 6
    assert "profile-warning.md" in result.warning
    assert (repo / ".artifacts" / "profile-warning.md").exists()
    assert "LM down" in (repo / ".artifacts" / "profile-warning.md").read_text(encoding="utf-8")
    assert "demo product" in (repo / ".artifacts" / "product.md").read_text(encoding="utf-8")


def test_add_workspace_passes_factory_built_reasoning(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    profiler = _RecordingProfiler()
    factory_configs = []

    def factory(config):
        factory_configs.append(config)
        return profiler

    add_workspace(
        "demo",
        repo,
        "Demo product",
        registry=WorkspaceRegistry(tmp_path / "state"),
        reasoning_factory=factory,
    )

    assert [config.name for config in factory_configs] == ["demo"]
    assert (repo / ".artifacts" / "rules.md").read_text(encoding="utf-8") == "agentic rules"


def test_add_workspace_surfaces_profile_warning_in_result(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")

    class _Exploding:
        def profile(self, **kwargs):
            raise RuntimeError("LM down")

    result = add_workspace(
        "demo",
        repo,
        "Demo product",
        registry=WorkspaceRegistry(tmp_path / "state"),
        reasoning_factory=lambda config: _Exploding(),
    )

    assert "profile-warning.md" in result.profile_warning
    assert "keyword fallback" in result.guidance
    assert (repo / ".artifacts" / "profile-warning.md").exists()


def test_profile_workspace_excludes_binary_docs_from_evidence(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    docs = repo / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("A textual guide.\n", encoding="utf-8")
    (docs / "intro.mdx").write_text("An MDX intro page.\n", encoding="utf-8")
    (docs / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)))
    config = default_workspace_config(
        name="demo", repo_path=str(repo), product_description="demo product"
    )
    profiler = _RecordingProfiler()

    profile_workspace(config, reasoning=profiler)

    repo_evidence = profiler.calls[0][0]
    assert "## docs/guide.md" in repo_evidence
    assert "## docs/intro.mdx" in repo_evidence
    assert "## docs/diagram.png" not in repo_evidence


def test_profile_workspace_caps_excerpt_budget_with_truncation_note(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    docs = repo / "docs"
    docs.mkdir()
    for index in range(45):
        (docs / f"doc-{index:02d}.md").write_text("x" * 4500, encoding="utf-8")
    config = default_workspace_config(
        name="demo", repo_path=str(repo), product_description="demo product"
    )
    profiler = _RecordingProfiler()

    result = profile_workspace(config, reasoning=profiler)

    repo_evidence = profiler.calls[0][0]
    assert len(repo_evidence) < 200_000
    assert "more sources omitted" in repo_evidence
    assert "## docs/doc-00.md" in repo_evidence
    assert "## docs/doc-44.md" not in repo_evidence
    assert result.warning == ""


def test_profile_workspace_unlinks_stale_warning_on_success(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    config = default_workspace_config(
        name="demo", repo_path=str(repo), product_description="demo product"
    )

    class _Exploding:
        def profile(self, **kwargs):
            raise RuntimeError("LM down")

    profile_workspace(config, reasoning=_Exploding())
    assert (repo / ".artifacts" / "profile-warning.md").exists()

    result = profile_workspace(config, reasoning=_RecordingProfiler())

    assert result.warning == ""
    assert not (repo / ".artifacts" / "profile-warning.md").exists()
