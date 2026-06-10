from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w

from bd1.errors import WorkspaceConfigError
from bd1.models import WorkspaceConfig

CONFIG_FILE = ".bd-1.toml"


def default_workspace_config(
    name: str,
    repo_path: str,
    product_description: str,
    setup_script: str = "",
    default_branch: str = "",
) -> WorkspaceConfig:
    return WorkspaceConfig(
        name=name,
        repo_path=str(Path(repo_path).expanduser().resolve()),
        default_branch=default_branch,
        product_description=product_description,
        setup_script=setup_script,
        max_attempts=5,
        pi_command="pi",
        pi_model="",
        pi_provider="",
        vet_command="vet",
        vet_model="flash",
        vet_confidence_threshold=0.8,
        dspy_model="openai/gpt-5-mini",
        dirty_exit_prompt="commit and resolve before exit",
        pr_command="gh",
        pr_monitor_wait_seconds=600,
        max_pr_feedback_attempts=3,
        max_pr_monitor_polls=6,
        pr_base_branch="",
        pr_draft=False,
        pr_comment_ignore_authors=[],
    )


def workspace_config_path(repo: str | Path) -> Path:
    return Path(repo) / CONFIG_FILE


def write_workspace_config(repo: str | Path, config: WorkspaceConfig) -> Path:
    path = workspace_config_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(config.to_dict()), encoding="utf-8")
    return path


def load_workspace_config(repo: str | Path) -> WorkspaceConfig:
    path = workspace_config_path(repo)
    if not path.exists():
        raise WorkspaceConfigError(f"Workspace config not found: {path}")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return WorkspaceConfig.from_dict(data)
