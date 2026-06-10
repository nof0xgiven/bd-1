import subprocess

import pytest

from bd1.errors import DirtyRepositoryError, GitError
from bd1.git import (
    branch_exists,
    create_worktree,
    default_branch,
    delete_branch,
    ensure_clean_repo,
    ensure_git_repo,
    get_head_commit,
    get_status_porcelain,
    remove_worktree,
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


def test_default_branch_prefers_origin_head(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    subprocess.run(
        ["git", "branch", "-M", "main"], cwd=repo, check=True, capture_output=True, text=True
    )
    remote = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote)],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "feature"], cwd=repo, check=True, capture_output=True, text=True
    )

    assert default_branch(repo) == "main"


def test_default_branch_falls_back_to_main_when_detached(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    head = get_head_commit(repo)
    subprocess.run(
        ["git", "checkout", "--detach", head], cwd=repo, check=True, capture_output=True, text=True
    )

    assert default_branch(repo) == "main"


def test_remove_worktree_and_delete_branch(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    base = get_head_commit(repo)
    worktree = tmp_path / "worktree"
    create_worktree(repo, worktree, "bd-1/cleanup", base)

    assert branch_exists(repo, "bd-1/cleanup")

    remove_worktree(repo, worktree)
    delete_branch(repo, "bd-1/cleanup")

    assert not worktree.exists()
    assert not branch_exists(repo, "bd-1/cleanup")
