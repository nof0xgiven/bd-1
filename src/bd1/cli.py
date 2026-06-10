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
from bd1.feedback import write_feedback, write_feedback_in_dir
from bd1.git import branch_exists, delete_branch, prune_worktrees, remove_worktree
from bd1.learning import ExampleStore, LearningStore, learning_records_from_output
from bd1.models import FeedbackRecord, RunState, WorkspaceConfig
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
    workspace_add.add_argument("--profile", choices=("agentic", "keyword"), default="agentic")
    workspace_subcommands.add_parser("list")
    workspace_profile = workspace_subcommands.add_parser("profile")
    workspace_profile.add_argument("workspace")
    workspace_profile.add_argument("--profile", choices=("agentic", "keyword"), default="agentic")

    run = subcommands.add_parser("run")
    run.add_argument("task", nargs="?")
    run.add_argument("--workspace")
    run.add_argument("--file")

    status = subcommands.add_parser("status")
    status.add_argument("run_id")

    clean = subcommands.add_parser("clean")
    clean.add_argument("run_id")

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

    doctor = subcommands.add_parser("doctor")
    doctor.add_argument("--workspace", default=None)

    return parser


def read_task_argument(task: str | None, task_file: str | None) -> str:
    if task and task_file:
        raise SystemExit("Use either a task argument or --file, not both.")
    if task_file:
        try:
            return Path(task_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise Bd1Error(f"Unable to read task file {task_file}: {exc}") from exc
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
        if args.command == "clean":
            return _handle_clean(args, registry, state_dir)
        if args.command == "feedback":
            return _handle_feedback(args, registry, state_dir)
        if args.command == "doctor":
            return _handle_doctor(args, registry)
        return 0
    except Bd1Error as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _handle_workspace(argparse_namespace: argparse.Namespace, registry: WorkspaceRegistry) -> int:
    if argparse_namespace.workspace_command == "add":
        reasoning_factory = None
        if argparse_namespace.profile == "agentic":
            reasoning_factory = _build_profile_reasoning
        result = add_workspace(
            argparse_namespace.name,
            argparse_namespace.repo,
            argparse_namespace.product,
            setup_script=argparse_namespace.setup_script,
            default_branch=argparse_namespace.default_branch,
            registry=registry,
            reasoning_factory=reasoning_factory,
        )
        print(result.guidance)
        return 0

    if argparse_namespace.workspace_command == "list":
        for workspace in registry.list_workspaces():
            print(f"{workspace.name}\t{workspace.repo_path}\t{workspace.product_description}")
        return 0

    if argparse_namespace.workspace_command == "profile":
        config = registry.get(argparse_namespace.workspace)
        reasoning = None
        if argparse_namespace.profile == "agentic":
            reasoning = _build_profile_reasoning(config)
        profile_workspace(config, reasoning=reasoning)
        print(f"Profile artifacts written for workspace {config.name}")
        return 0

    parser_error = f"Unknown workspace command: {argparse_namespace.workspace_command}"
    raise SystemExit(parser_error)


def _build_profile_reasoning(config: WorkspaceConfig):
    try:
        return _build_reasoning(config)
    except WorkspaceConfigError:
        return None  # keyword fallback; doctor reports the missing dspy_model


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
    return 0 if record.state is RunState.COMPLETE and record.final_verdict == "PASS" else 2


def _handle_status(args: argparse.Namespace, state_dir: Path) -> int:
    run_store = RunStore(state_dir)
    record = run_store.read_by_id(args.run_id)
    RunIndex(state_dir / "runs.db").upsert_run(record)
    print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
    return 0


def _handle_clean(
    args: argparse.Namespace,
    registry: WorkspaceRegistry,
    state_dir: Path,
) -> int:
    run_store = RunStore(state_dir)
    record = run_store.read_by_id(args.run_id)
    if record.state not in (RunState.COMPLETE, RunState.BLOCKED):
        raise Bd1Error(
            f"Run {record.run_id} is in state {record.state.value}; "
            "only COMPLETE or BLOCKED runs can be cleaned."
        )

    run_store.archive(record)

    config = registry.get(record.workspace)
    repo = Path(config.repo_path)
    worktree = Path(record.worktree)
    worktree_removed = False
    if worktree.exists():
        remove_worktree(repo, worktree)
        worktree_removed = True
    else:
        prune_worktrees(repo)

    branch_deleted = False
    if record.branch and branch_exists(repo, record.branch):
        delete_branch(repo, record.branch)
        branch_deleted = True

    print(
        json.dumps(
            {
                "run_id": record.run_id,
                "archived_to": str(run_store.archive_dir(record.run_id)),
                "worktree_removed": worktree_removed,
                "branch_deleted": branch_deleted,
            },
            sort_keys=True,
        )
    )
    return 0


def _handle_feedback(
    args: argparse.Namespace,
    registry: WorkspaceRegistry,
    state_dir: Path,
) -> int:
    run_store = RunStore(state_dir)
    record = run_store.read_by_id(args.run_id)
    worktree = Path(record.worktree)
    worktree_exists = worktree.is_dir()
    learning_store = LearningStore.for_workspace(state_dir, record.workspace)
    example_store = ExampleStore.for_workspace(state_dir, record.workspace)

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
    if worktree_exists:
        feedback_path = write_feedback(worktree, feedback)
    else:
        feedback_path = write_feedback_in_dir(run_store.archive_dir(record.run_id), feedback)
    feedback_paths = list(record.feedback_paths)
    if str(feedback_path) not in feedback_paths:
        feedback_paths.append(str(feedback_path))
    updated = replace(record, feedback_paths=feedback_paths)
    if worktree_exists:
        run_store.write(worktree, updated)
    else:
        run_store.write_archived(updated)

    reasoning = _build_reasoning_for_run(record.workspace, registry)
    evidence = collect_evidence(worktree, task=record.task, learning_store=learning_store)
    learning = reasoning.learn(
        evidence,
        review_markdown=(
            "feedback: "
            f"outcome={feedback.outcome}; wrong_or_missing={feedback.wrong_or_missing}; "
            f"expected={feedback.expected}"
        ),
    )
    if worktree_exists:
        learning_path = worktree / ".artifacts" / "learning" / f"{record.run_id}-feedback.md"
        write_text(learning_path, learning.markdown, redact=True)
    for learning_record in learning_records_from_output(
        learning.learnings, run_id=record.run_id, task=record.task, event="feedback"
    ):
        learning_store.save_learning(learning_record)
    example_store.append_example(
        "learning",
        {"run_id": record.run_id, "event": "feedback", "markdown": learning.markdown},
    )
    learning_store.write_terminal_summary(example_store)
    summary = learning_store.terminal_summary(example_store)
    print(str(feedback_path))
    print(
        "learnings: "
        f"active={summary['active']} pending={summary['pending']} "
        f"rejected={summary['rejected']} superseded={summary['superseded']} "
        f"examples={summary['examples'].get('total', 0)}"
    )
    if summary["corrupt_files"]:
        print(
            "warning: skipped corrupt learning files: " + ", ".join(summary["corrupt_files"]),
            file=sys.stderr,
        )
    return 0


def _handle_doctor(args: argparse.Namespace, registry: WorkspaceRegistry) -> int:
    import shlex

    from bd1.doctor import run_checks
    from bd1.subprocesses import run_command

    config = resolve_workspace(args.workspace, Path.cwd(), registry)
    binaries = tuple(
        shlex.split(command)[0]
        for command in ("git", config.pi_command, config.vet_command, config.pr_command)
        if command.strip()
    )
    results = run_checks(binaries=binaries, runner=run_command, dspy_model=config.dspy_model)
    for result in results:
        print(f"{'ok ' if result.ok else 'FAIL'} {result.name}: {result.detail}")
    return 0 if all(result.ok for result in results) else 1


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

    dspy.configure(lm=dspy.LM(config.dspy_model, num_retries=config.dspy_num_retries))
    return DspyReasoningPrograms(discovery_max_iters=config.discovery_max_iters)
