from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def hermetic_git_env() -> dict[str, str]:
    """Environment that shields git from the developer's global/system config.

    Duplicated in tests/fakes.py because conftest.py loads before the tests
    package is importable.
    """
    return {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def make_git_repo(path: Path) -> Path:
    env = hermetic_git_env()
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=path, check=True, env=env
    )
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True, env=env)
    (path / "README.md").write_text("# Fixture\n\nA fixture repo.\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return path


@pytest.fixture
def init_git_repo():
    return make_git_repo
