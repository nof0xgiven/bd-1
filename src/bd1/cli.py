from __future__ import annotations

import argparse
from pathlib import Path


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
    parser.parse_args(argv)
    return 0
