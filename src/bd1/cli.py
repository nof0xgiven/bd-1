from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from bd1.artifacts import write_text
from bd1.config import CONFIG_FILE, load_workspace_config
from bd1.dspy_programs import DspyReasoningPrograms, TemplateReasoningPrograms
from bd1.errors import Bd1Error, WorkspaceConfigError
from bd1.evidence import collect_evidence
from bd1.feedback import write_feedback
from bd1.learning import ExampleStore, LearningStore
from bd1.models import FeedbackRecord, WorkspaceConfig
from bd1.orchestrator import Orchestrator
from bd1.paths import global_state_dir
from bd1.registry import WorkspaceRegistry
from bd1.run_index import RunIndex
from bd1.run_store import RunStore, now_iso
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
    state_dir = global_state_dir()
    registry = WorkspaceRegistry(state_dir)

    try:
        if args.command == "workspace":
            return _handle_workspace(args, registry)
        if args.command == "run":
            return _handle_run(args, registry, state_dir)
        if args.command == "status":
            return _handle_status(args, state_dir)
        if args.command == "feedback":
            return _handle_feedback(args, registry, state_dir)
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


def resolve_workspace(
    explicit_workspace: str | None,
    cwd: str | Path,
    registry: WorkspaceRegistry,
) -> WorkspaceConfig:
    if explicit_workspace:
        return registry.get(explicit_workspace)

    current = Path(cwd).resolve()
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_FILE).exists():
            return load_workspace_config(candidate)

    workspaces = registry.list_workspaces()
    if len(workspaces) == 1:
        return workspaces[0]

    available = ", ".join(workspace.name for workspace in workspaces) or "none"
    raise WorkspaceConfigError(
        f"Use --workspace when running outside a registered workspace. Available: {available}"
    )


def _handle_run(
    args: argparse.Namespace,
    registry: WorkspaceRegistry,
    state_dir: Path,
) -> int:
    task = read_task_argument(args.task, args.file)
    config = resolve_workspace(args.workspace, Path.cwd(), registry)
    reasoning = _build_reasoning(config)
    record = Orchestrator(global_root=state_dir, reasoning=reasoning).run(config, task)
    print(json.dumps({"run_id": record.run_id, "state": record.state.value}, sort_keys=True))
    return 0


def _handle_status(args: argparse.Namespace, state_dir: Path) -> int:
    run_store = RunStore(state_dir)
    record = run_store.read_by_id(args.run_id)
    RunIndex(state_dir / "runs.db").upsert_run(record)
    print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
    return 0


def _handle_feedback(
    args: argparse.Namespace,
    registry: WorkspaceRegistry,
    state_dir: Path,
) -> int:
    run_store = RunStore(state_dir)
    record = run_store.read_by_id(args.run_id)
    repo_path = Path(record.worktree)
    feedback = FeedbackRecord(
        run_id=record.run_id,
        created_at=now_iso(),
        outcome=args.outcome,
        wrong_or_missing=args.wrong_or_missing,
        expected=args.expected,
        affected_artifact=args.affected_artifact,
        commit=args.commit,
        learning_candidate=args.learning_candidate,
    )
    feedback_path = write_feedback(repo_path, feedback)
    updated = replace(record, feedback_paths=[*record.feedback_paths, str(feedback_path)])
    run_store.write(repo_path, updated)

    reasoning = _build_reasoning_for_run(record.workspace, registry)
    evidence = collect_evidence(repo_path, task=record.task)
    learning = reasoning.learn(
        evidence,
        review_markdown=(
            "feedback: "
            f"outcome={feedback.outcome}; wrong_or_missing={feedback.wrong_or_missing}; "
            f"expected={feedback.expected}"
        ),
    )
    learning_path = repo_path / ".artifacts" / "learning" / f"{record.run_id}-feedback.md"
    write_text(learning_path, learning.markdown, redact=True)
    ExampleStore(repo_path).append_example(
        "learning",
        {"run_id": record.run_id, "event": "feedback", "markdown": learning.markdown},
    )
    LearningStore(repo_path).write_terminal_summary()
    print(str(feedback_path))
    return 0


def _build_reasoning_for_run(workspace_name: str, registry: WorkspaceRegistry):
    if os.environ.get("BD1_REASONING") == "template":
        return TemplateReasoningPrograms()
    return _build_reasoning(registry.get(workspace_name))


def _build_reasoning(config: WorkspaceConfig):
    if os.environ.get("BD1_REASONING") == "template":
        return TemplateReasoningPrograms()
    if not config.dspy_model.strip():
        raise WorkspaceConfigError(
            "Live DSPy reasoning requires dspy_model in .bd-1.toml. "
            "Set BD1_REASONING=template only for tests."
        )
    import dspy

    dspy.configure(lm=dspy.LM(config.dspy_model))
    return DspyReasoningPrograms()
