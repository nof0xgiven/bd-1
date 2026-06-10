from __future__ import annotations

from pathlib import Path

from bd1.errors import DirtyRepositoryError, GitError
from bd1.subprocesses import CommandResult, run_command

GIT_TIMEOUT_SECONDS = 120.0


def git(repo: str | Path, args: list[str]) -> CommandResult:
    repo_path = Path(repo)
    if not repo_path.exists() or not repo_path.is_dir():
        raise GitError(f"Repository path does not exist: {repo_path}")

    result = run_command(["git", *args], cwd=repo_path, timeout=GIT_TIMEOUT_SECONDS)
    if result.exit_code != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise GitError(message or f"git {' '.join(args)} failed")
    return result


def ensure_git_repo(repo: str | Path) -> None:
    git(repo, ["rev-parse", "--show-toplevel"])


def get_status_porcelain(repo: str | Path) -> list[str]:
    return [
        line for line in git(repo, ["status", "--porcelain"]).stdout.splitlines() if line.strip()
    ]


def ensure_clean_repo(repo: str | Path) -> None:
    entries = get_status_porcelain(repo)
    if entries:
        raise DirtyRepositoryError("Repository has uncommitted changes:\n" + "\n".join(entries))


def get_head_commit(repo: str | Path) -> str:
    return git(repo, ["rev-parse", "HEAD"]).stdout.strip()


def default_branch(repo: str | Path) -> str:
    origin_head = run_command(
        ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        cwd=Path(repo),
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if origin_head.exit_code == 0:
        ref = origin_head.stdout.strip()
        if ref.startswith("refs/remotes/origin/"):
            return ref.removeprefix("refs/remotes/origin/")
    branch = git(repo, ["branch", "--show-current"]).stdout.strip()
    return branch or "main"


def create_worktree(repo: str | Path, worktree: str | Path, branch: str, base_commit: str) -> None:
    Path(worktree).parent.mkdir(parents=True, exist_ok=True)
    git(repo, ["worktree", "add", "-b", branch, str(worktree), base_commit])


def diff_from_base(repo: str | Path, base_commit: str) -> str:
    return git(repo, ["diff", f"{base_commit}...HEAD"]).stdout


def remove_worktree(repo: str | Path, worktree: str | Path) -> None:
    git(repo, ["worktree", "remove", "--force", str(worktree)])


def prune_worktrees(repo: str | Path) -> None:
    git(repo, ["worktree", "prune"])


def branch_exists(repo: str | Path, branch: str) -> bool:
    result = run_command(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=Path(repo),
        timeout=GIT_TIMEOUT_SECONDS,
    )
    return result.exit_code == 0


def delete_branch(repo: str | Path, branch: str) -> None:
    git(repo, ["branch", "-D", branch])
