import subprocess

import pytest

from bd1.errors import DirtyRepositoryError, GitError
from bd1.git import (
    create_worktree,
    default_branch,
    ensure_clean_repo,
    ensure_git_repo,
    get_head_commit,
    get_status_porcelain,
)


def test_ensure_git_repo_rejects_missing_path(tmp_path):
    with pytest.raises(GitError):
        ensure_git_repo(tmp_path / "missing")


def test_dirty_repo_reports_files(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    (repo / "README.md").write_text("# Changed\n", encoding="utf-8")

    with pytest.raises(DirtyRepositoryError) as exc:
        ensure_clean_repo(repo)

    assert "README.md" in str(exc.value)


def test_create_worktree_creates_branch(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    base = get_head_commit(repo)
    worktree = tmp_path / "worktree"

    create_worktree(repo, worktree, "bd-1/test-branch", base)

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch == "bd-1/test-branch"


def test_default_branch_uses_current_branch(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")

    assert default_branch(repo) in {"main", "master"}
    assert get_status_porcelain(repo) == []
