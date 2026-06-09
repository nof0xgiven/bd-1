from __future__ import annotations

from pathlib import Path

from bd1.errors import DirtyRepositoryError, GitError
from bd1.subprocesses import CommandResult, run_command


def git(repo: str | Path, args: list[str]) -> CommandResult:
    repo_path = Path(repo)
    if not repo_path.exists() or not repo_path.is_dir():
        raise GitError(f"Repository path does not exist: {repo_path}")

    result = run_command(["git", *args], cwd=repo_path)
    if result.exit_code != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise GitError(message or f"git {' '.join(args)} failed")
    return result


def ensure_git_repo(repo: str | Path) -> None:
    git(repo, ["rev-parse", "--show-toplevel"])


def get_status_porcelain(repo: str | Path) -> list[str]:
    return [line for line in git(repo, ["status", "--porcelain"]).stdout.splitlines() if line.strip()]


def ensure_clean_repo(repo: str | Path) -> None:
    entries = get_status_porcelain(repo)
    if entries:
        raise DirtyRepositoryError("Repository has uncommitted changes:\n" + "\n".join(entries))


def get_head_commit(repo: str | Path) -> str:
    return git(repo, ["rev-parse", "HEAD"]).stdout.strip()


def default_branch(repo: str | Path) -> str:
    branch = git(repo, ["branch", "--show-current"]).stdout.strip()
    return branch or "main"


def create_worktree(repo: str | Path, worktree: str | Path, branch: str, base_commit: str) -> None:
    Path(worktree).parent.mkdir(parents=True, exist_ok=True)
    git(repo, ["worktree", "add", "-b", branch, str(worktree), base_commit])


def diff_from_base(repo: str | Path, base_commit: str) -> str:
    return git(repo, ["diff", f"{base_commit}...HEAD"]).stdout
