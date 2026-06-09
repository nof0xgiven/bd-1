from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bd1.errors import Bd1Error
from bd1.paths import global_state_dir
from bd1.registry import WorkspaceRegistry
from bd1.workspace import add_workspace, profile_workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bd-1")
    subcommands = parser.add_subparsers(dest="command", required=True)

    workspace = subcommands.add_parser("workspace")
    workspace_subcommands = workspace.add_subparsers(dest="workspace_command", required=True)
    workspace_add = workspace_subcommands.add_parser("add")
    workspace_add.add_argument("--name", required=True)
    workspace_add.add_argument("--repo", required=True)
    workspace_add.add_argument("--product", required=True)
    workspace_add.add_argument("--setup-script", default="")
    workspace_add.add_argument("--default-branch", default="")
    workspace_subcommands.add_parser("list")
    workspace_profile = workspace_subcommands.add_parser("profile")
    workspace_profile.add_argument("workspace")

    run = subcommands.add_parser("run")
    run.add_argument("task", nargs="?")
    run.add_argument("--workspace")
    run.add_argument("--file")

    status = subcommands.add_parser("status")
    status.add_argument("run_id")

    feedback = subcommands.add_parser("feedback")
    feedback.add_argument("run_id")
    feedback.add_argument("--outcome", required=True)
    feedback.add_argument("--wrong-or-missing", required=True)
    feedback.add_argument("--expected", required=True)
    feedback.add_argument("--affected-artifact", default="")
    feedback.add_argument("--commit", default="")
    feedback.add_argument(
        "--learning-candidate", action=argparse.BooleanOptionalAction, default=True
    )

    return parser


def read_task_argument(task: str | None, task_file: str | None) -> str:
    if task and task_file:
        raise SystemExit("Use either a task argument or --file, not both.")
    if task_file:
        return Path(task_file).read_text(encoding="utf-8").strip()
    if task:
        return task.strip()
    raise SystemExit("A task argument or --file is required.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    registry = WorkspaceRegistry(global_state_dir())

    try:
        if args.command == "workspace":
            return _handle_workspace(args, registry)
        return 0
    except Bd1Error as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _handle_workspace(argparse_namespace: argparse.Namespace, registry: WorkspaceRegistry) -> int:
    if argparse_namespace.workspace_command == "add":
        result = add_workspace(
            argparse_namespace.name,
            argparse_namespace.repo,
            argparse_namespace.product,
            setup_script=argparse_namespace.setup_script,
            default_branch=argparse_namespace.default_branch,
            registry=registry,
        )
        print(result.guidance)
        return 0

    if argparse_namespace.workspace_command == "list":
        for workspace in registry.list_workspaces():
            print(f"{workspace.name}\t{workspace.repo_path}\t{workspace.product_description}")
        return 0

    if argparse_namespace.workspace_command == "profile":
        config = registry.get(argparse_namespace.workspace)
        profile_workspace(config)
        print(f"Profile artifacts written for workspace {config.name}")
        return 0

    parser_error = f"Unknown workspace command: {argparse_namespace.workspace_command}"
    raise SystemExit(parser_error)
