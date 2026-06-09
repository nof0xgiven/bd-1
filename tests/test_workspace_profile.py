import subprocess

import pytest

from bd1.errors import DirtyRepositoryError
from bd1.registry import WorkspaceRegistry
from bd1.workspace import add_workspace, profile_workspace


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
