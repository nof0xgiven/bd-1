from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bd1.artifacts import write_text
from bd1.errors import PrError
from bd1.subprocesses import CommandResult, run_command

CommandRunner = Callable[[list[str], str | Path], CommandResult]
Sleeper = Callable[[float], None]


@dataclass(frozen=True)
class PrCheck:
    name: str
    bucket: str
    state: str
    link: str
    description: str


@dataclass(frozen=True)
class PrFeedbackItem:
    key: str
    source: str
    author: str
    body: str
    path: str
    url: str
    required_action: str
    created_at: str = ""
    updated_at: str = ""
    commit_id: str = ""


@dataclass(frozen=True)
class PrPublication:
    number: int
    url: str
    state: str


@dataclass(frozen=True)
class PrResult:
    number: int
    url: str
    state: str
    checks: list[PrCheck]
    feedback: list[PrFeedbackItem]
    merge_conflict: bool
    artifact_path: str = ""
    complete_artifact_path: str = ""


class PrRunner:
    def __init__(
        self,
        *,
        pr_command: str = "gh",
        command_runner: CommandRunner = run_command,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        self.pr_command = pr_command
        self.command_runner = command_runner
        self.sleeper = sleeper

    def publish_or_update(
        self,
        *,
        worktree: Path,
        task: str,
        branch: str,
        base_branch: str,
        run_id: str,
        base_commit: str,
        completed_path: Path,
        review_path: Path,
        draft: bool,
    ) -> PrPublication:
        worktree = Path(worktree)
        self._run(["git", "push", "-u", "origin", branch], worktree, label="git push")
        body_path = self._write_body(
            worktree=worktree,
            task=task,
            branch=branch,
            base_branch=base_branch,
            run_id=run_id,
            base_commit=base_commit,
            completed_path=Path(completed_path),
            review_path=Path(review_path),
        )

        existing = self._find_open_pr(worktree, branch)
        if existing is not None:
            number = self._pr_number(existing, context=f"{self.pr_command} pr list")
            self._run(
                [
                    self.pr_command,
                    "pr",
                    "edit",
                    str(number),
                    "--title",
                    self._title(task),
                    "--body-file",
                    str(body_path),
                ],
                worktree,
                label=f"{self.pr_command} pr edit",
            )
            return PrPublication(
                number=number,
                url=str(existing.get("url", "")),
                state=str(existing.get("state", "OPEN") or "OPEN"),
            )

        create_command = [
            self.pr_command,
            "pr",
            "create",
            "--title",
            self._title(task),
            "--body-file",
            str(body_path),
            "--head",
            branch,
        ]
        if base_branch:
            create_command.extend(["--base", base_branch])
        if draft:
            create_command.append("--draft")
        create_result = self._run(create_command, worktree, label=f"{self.pr_command} pr create")

        created = self._find_open_pr(worktree, branch)
        if created is None:
            number = _pull_number_from_url(create_result.stdout.strip())
            if number is None:
                raise PrError(f"{self.pr_command} pr create did not return an open PR")
            return PrPublication(number=number, url=create_result.stdout.strip(), state="OPEN")

        return PrPublication(
            number=self._pr_number(created, context=f"{self.pr_command} pr list"),
            url=str(created.get("url", "")),
            state=str(created.get("state", "OPEN") or "OPEN"),
        )

    def monitor(
        self,
        *,
        worktree: Path,
        task: str,
        task_slug: str,
        publication: PrPublication,
        branch: str,
        feedback_number: int,
        wait_seconds: int,
        seen_feedback_keys: set[str],
    ) -> PrResult:
        worktree = Path(worktree)
        if wait_seconds > 0:
            self.sleeper(wait_seconds)

        details = self._pr_details(worktree, publication.number)
        checks = self._checks(worktree, publication.number)
        owner_repo = _owner_repo_from_url(str(details.get("url") or publication.url))
        review_comments = self._comments(
            worktree,
            ["repos", owner_repo, "pulls", str(publication.number), "comments"],
            context=f"{self.pr_command} api review comments",
        )
        issue_comments = self._comments(
            worktree,
            ["repos", owner_repo, "issues", str(publication.number), "comments"],
            context=f"{self.pr_command} api issue comments",
        )

        feedback, merge_conflict = self._feedback_from_details(details)
        feedback.extend(self._feedback_from_checks(checks))
        feedback.extend(self._feedback_from_reviews(details))
        feedback.extend(self._feedback_from_review_comments(review_comments))
        feedback.extend(self._feedback_from_issue_comments(issue_comments))
        filtered_feedback = [
            item for item in feedback if _should_emit_feedback(item, seen_feedback_keys)
        ]

        artifact_path = ""
        complete_artifact_path = ""
        if filtered_feedback:
            artifact_path = str(
                self._write_feedback_artifact(
                    worktree=worktree,
                    task=task,
                    task_slug=task_slug,
                    branch=branch,
                    publication=publication,
                    feedback_number=feedback_number,
                    checks=checks,
                    feedback=filtered_feedback,
                    merge_conflict=merge_conflict,
                )
            )
        else:
            complete_artifact_path = str(
                self._write_complete_artifact(
                    worktree=worktree,
                    task=task,
                    task_slug=task_slug,
                    publication=publication,
                    feedback_number=feedback_number,
                    checks=checks,
                )
            )

        return PrResult(
            number=int(details.get("number") or publication.number),
            url=str(details.get("url") or publication.url),
            state=str(details.get("state") or publication.state),
            checks=checks,
            feedback=filtered_feedback,
            merge_conflict=merge_conflict,
            artifact_path=artifact_path,
            complete_artifact_path=complete_artifact_path,
        )

    def _run(
        self,
        command: list[str],
        cwd: Path,
        *,
        label: str,
        allowed_exit_codes: set[int] | None = None,
    ) -> CommandResult:
        try:
            result = self.command_runner(command, cwd)
        except OSError as exc:
            raise PrError(f"Unable to start command: {' '.join(command)}: {exc}") from exc

        allowed = allowed_exit_codes or {0}
        if result.exit_code not in allowed:
            message = result.stderr.strip() or result.stdout.strip()
            raise PrError(f"{label} failed: {message or f'exit {result.exit_code}'}")
        return result

    def _write_body(
        self,
        *,
        worktree: Path,
        task: str,
        branch: str,
        base_branch: str,
        run_id: str,
        base_commit: str,
        completed_path: Path,
        review_path: Path,
    ) -> Path:
        completed_text = _read_optional(completed_path)
        review_text = _read_optional(review_path)
        body = "\n".join(
            [
                "## Summary",
                "",
                f"- Task: {task}",
                f"- Branch: `{branch}`",
                f"- Base branch: `{base_branch or 'default'}`",
                f"- Run: `{run_id}`",
                f"- Base commit: `{base_commit}`",
                "",
                "## Validation",
                "",
                f"- Completion artifact: `{_relative_to(completed_path, worktree)}`",
                f"- Review artifact: `{_relative_to(review_path, worktree)}`",
                "",
                "## Risk",
                "",
                "- Low: PR body generated from bd-1 completion and review artifacts.",
                "",
                "## Completion Artifact",
                "",
                completed_text.strip() or "_No completion artifact content._",
                "",
                "## Review Artifact",
                "",
                review_text.strip() or "_No review artifact content._",
                "",
            ]
        )
        return write_text(worktree / ".artifacts" / "pr" / "body.md", body)

    def _find_open_pr(self, worktree: Path, branch: str) -> dict[str, Any] | None:
        command = [
            self.pr_command,
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number,url,title,headRefName,baseRefName,state",
        ]
        result = self._run(command, worktree, label=f"{self.pr_command} pr list")
        items = _json_list(result.stdout, context=f"{self.pr_command} pr list")
        if not items:
            return None
        first = items[0]
        if not isinstance(first, dict):
            raise PrError(f"Invalid JSON shape from {self.pr_command} pr list: expected objects")
        return first

    def _pr_details(self, worktree: Path, number: int) -> dict[str, Any]:
        result = self._run(
            [
                self.pr_command,
                "pr",
                "view",
                str(number),
                "--json",
                "number,url,state,mergeable,reviewDecision,reviews,headRefName,baseRefName",
            ],
            worktree,
            label=f"{self.pr_command} pr view",
        )
        return _json_object(result.stdout, context=f"{self.pr_command} pr view")

    def _checks(self, worktree: Path, number: int) -> list[PrCheck]:
        command = [
            self.pr_command,
            "pr",
            "checks",
            str(number),
            "--json",
            "name,state,bucket,link,description,startedAt,completedAt",
        ]
        result = self._run(
            command,
            worktree,
            label=f"{self.pr_command} pr checks",
            allowed_exit_codes={0, 1, 8},
        )
        if result.exit_code != 0 and not result.stdout.strip():
            raise PrError(f"{self.pr_command} pr checks returned no JSON")
        items = _json_list(result.stdout, context=f"{self.pr_command} pr checks")
        checks = []
        for item in items:
            if not isinstance(item, dict):
                raise PrError(
                    f"Invalid JSON shape from {self.pr_command} pr checks: expected objects"
                )
            checks.append(
                PrCheck(
                    name=str(item.get("name", "")),
                    bucket=str(item.get("bucket", "")),
                    state=str(item.get("state", "")),
                    link=str(item.get("link", "")),
                    description=str(item.get("description", "")),
                )
            )
        return checks

    def _comments(
        self, worktree: Path, path_parts: list[str], *, context: str
    ) -> list[dict[str, Any]]:
        result = self._run(
            [self.pr_command, "api", "/".join(path_parts), "--paginate", "--slurp"],
            worktree,
            label=context,
        )
        return _json_slurped_list(result.stdout, context=context)

    def _feedback_from_details(self, details: dict[str, Any]) -> tuple[list[PrFeedbackItem], bool]:
        mergeable = str(details.get("mergeable", "") or "")
        if mergeable == "CONFLICTING":
            return (
                [
                    PrFeedbackItem(
                        key="mergeability:CONFLICTING",
                        source="mergeability",
                        author="github",
                        body="GitHub reports this branch has merge conflicts.",
                        path="",
                        url=str(details.get("url", "")),
                        required_action="Resolve merge conflicts before PR completion.",
                    )
                ],
                True,
            )
        if mergeable == "UNKNOWN":
            return (
                [
                    PrFeedbackItem(
                        key="mergeability:UNKNOWN",
                        source="mergeability",
                        author="github",
                        body="GitHub has not resolved mergeability for this PR yet.",
                        path="",
                        url=str(details.get("url", "")),
                        required_action="Wait for mergeability to resolve or inspect the PR.",
                    )
                ],
                False,
            )
        return ([], False)

    def _feedback_from_checks(self, checks: list[PrCheck]) -> list[PrFeedbackItem]:
        feedback = []
        for check in checks:
            if _check_passed(check):
                continue
            required_action = _check_required_action(check)
            feedback.append(
                PrFeedbackItem(
                    key=f"ci:{check.name}",
                    source="ci",
                    author="github",
                    body=check.description or check.state or check.bucket,
                    path=check.name,
                    url=check.link,
                    required_action=required_action,
                )
            )
        return feedback

    def _feedback_from_reviews(self, details: dict[str, Any]) -> list[PrFeedbackItem]:
        reviews = details.get("reviews", [])
        if not isinstance(reviews, list):
            raise PrError(f"Invalid JSON shape from {self.pr_command} pr view: reviews")
        feedback = []
        review_decision = str(details.get("reviewDecision", ""))
        for review in reviews:
            if not isinstance(review, dict):
                raise PrError(f"Invalid JSON shape from {self.pr_command} pr view: reviews")
            if str(review.get("state", "")) != "CHANGES_REQUESTED":
                continue
            body = str(review.get("body", "") or "").strip()
            if not body:
                continue
            identifier = review.get("id") or review.get("url") or review.get("state")
            author = _login(review.get("author"))
            commit = review.get("commit")
            commit_id = ""
            if isinstance(commit, dict):
                commit_id = str(commit.get("oid", "") or "")
            feedback.append(
                PrFeedbackItem(
                    key=f"review-summary:{identifier}",
                    source=(
                        "review-decision" if review_decision == "CHANGES_REQUESTED" else "review"
                    ),
                    author=author,
                    body=body,
                    path="",
                    url=str(review.get("url", "") or ""),
                    required_action="Address the changes requested in this review.",
                    created_at=str(review.get("submittedAt", "") or ""),
                    updated_at=str(review.get("submittedAt", "") or ""),
                    commit_id=commit_id,
                )
            )
        if review_decision == "CHANGES_REQUESTED" and not feedback:
            feedback.append(
                PrFeedbackItem(
                    key="review-decision:CHANGES_REQUESTED",
                    source="review-decision",
                    author="github",
                    body="GitHub reviewDecision is CHANGES_REQUESTED, but no review body was available.",
                    path="",
                    url=str(details.get("url", "") or ""),
                    required_action="Inspect the PR review state and address requested changes.",
                )
            )
        return feedback

    def _feedback_from_review_comments(
        self, comments: list[dict[str, Any]]
    ) -> list[PrFeedbackItem]:
        feedback = []
        for comment in comments:
            identifier = comment.get("id") or comment.get("html_url") or comment.get("url")
            feedback.append(
                PrFeedbackItem(
                    key=f"review:{identifier}",
                    source="review",
                    author=_login(comment.get("user")),
                    body=str(comment.get("body", "") or ""),
                    path=str(comment.get("path", "") or ""),
                    url=str(comment.get("html_url") or comment.get("url") or ""),
                    required_action="Address this PR review comment.",
                    created_at=str(comment.get("created_at", "") or ""),
                    updated_at=str(comment.get("updated_at", "") or ""),
                    commit_id=str(comment.get("commit_id", "") or ""),
                )
            )
        return feedback

    def _feedback_from_issue_comments(self, comments: list[dict[str, Any]]) -> list[PrFeedbackItem]:
        feedback = []
        for comment in comments:
            identifier = comment.get("id") or comment.get("html_url") or comment.get("url")
            feedback.append(
                PrFeedbackItem(
                    key=f"conversation:{identifier}",
                    source="conversation",
                    author=_login(comment.get("user")),
                    body=str(comment.get("body", "") or ""),
                    path="",
                    url=str(comment.get("html_url") or comment.get("url") or ""),
                    required_action="Address this PR conversation comment.",
                    created_at=str(comment.get("created_at", "") or ""),
                    updated_at=str(comment.get("updated_at", "") or ""),
                )
            )
        return feedback

    def _write_feedback_artifact(
        self,
        *,
        worktree: Path,
        task: str,
        task_slug: str,
        branch: str,
        publication: PrPublication,
        feedback_number: int,
        checks: list[PrCheck],
        feedback: list[PrFeedbackItem],
        merge_conflict: bool,
    ) -> Path:
        path = worktree / ".artifacts" / "pr" / f"{task_slug}-{feedback_number}.md"
        lines = [
            f"# PR Feedback: {task}",
            "",
            "## Status",
            "",
            "BLOCKED" if merge_conflict else "OPEN",
            "",
            f"PR: {publication.url}",
            f"Branch: `{branch}`",
            "",
            "---",
            "",
            "## CI / Pipeline Failures",
            "",
            "| Check | Status | Failure | Required Action |",
            "|---|---|---|---|",
        ]
        ci_items = [item for item in feedback if item.source == "ci"]
        if ci_items:
            for item in ci_items:
                check = _check_by_name(checks, item.path)
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _md(item.path),
                            _md(_check_status(check)),
                            _md(item.body),
                            _md(item.required_action),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("| None | pass |  |  |")

        lines.extend(
            [
                "",
                "---",
                "",
                "## Review Comments",
                "",
                "| Source | Author | Path | Comment | Required Action |",
                "|---|---|---|---|---|",
            ]
        )
        review_items = [item for item in feedback if item.source != "ci"]
        if review_items:
            for item in review_items:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _md(item.source),
                            _md(item.author),
                            _md(item.path),
                            _md(item.body),
                            _md(item.required_action),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("| None |  |  |  |  |")

        lines.extend(["", "---", "", "## Consolidated Resolve Prompt", ""])
        lines.append(f"Resolve PR feedback for `{task}` on branch `{branch}`.")
        lines.append("")
        for item in feedback:
            target = f" ({item.path})" if item.path else ""
            lines.append(
                f"- [{item.source}] {item.author}{target}: {item.body} "
                f"Required action: {item.required_action}"
            )
        lines.append("")
        return write_text(path, "\n".join(lines))

    def _write_complete_artifact(
        self,
        *,
        worktree: Path,
        task: str,
        task_slug: str,
        publication: PrPublication,
        feedback_number: int,
        checks: list[PrCheck],
    ) -> Path:
        path = worktree / ".artifacts" / "pr" / f"{task_slug}-{feedback_number}-complete.md"
        lines = [
            f"# PR Feedback Complete: {task}",
            "",
            f"PR: {publication.url}",
            "",
            "No unprocessed CI, review, mergeability, or PR conversation feedback remains.",
            "",
            "## Checks",
            "",
            "| Check | Status | Failure | Required Action |",
            "|---|---|---|---|",
        ]
        if checks:
            for check in checks:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _md(check.name),
                            _md(_check_status(check)),
                            "",
                            "",
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("| None | pass |  |  |")
        lines.append("")
        return write_text(path, "\n".join(lines))

    def _pr_number(self, data: dict[str, Any], *, context: str) -> int:
        try:
            return int(data["number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PrError(f"Invalid JSON shape from {context}: missing number") from exc

    def _title(self, task: str) -> str:
        return f"bd-1: {task}"


def _json_loads(text: str, *, context: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PrError(f"Invalid JSON from {context}: {exc.msg}") from exc


def _json_object(text: str, *, context: str) -> dict[str, Any]:
    data = _json_loads(text, context=context)
    if not isinstance(data, dict):
        raise PrError(f"Invalid JSON shape from {context}: expected object")
    return data


def _json_list(text: str, *, context: str) -> list[Any]:
    data = _json_loads(text, context=context)
    if not isinstance(data, list):
        raise PrError(f"Invalid JSON shape from {context}: expected list")
    return data


def _json_slurped_list(text: str, *, context: str) -> list[dict[str, Any]]:
    data = _json_loads(text, context=context)
    if not isinstance(data, list):
        raise PrError(f"Invalid JSON shape from {context}: expected list")

    flattened: list[Any] = []
    for item in data:
        if isinstance(item, list):
            flattened.extend(item)
        else:
            flattened.append(item)

    comments = []
    for item in flattened:
        if not isinstance(item, dict):
            raise PrError(f"Invalid JSON shape from {context}: expected objects")
        comments.append(item)
    return comments


def _owner_repo_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise PrError(f"Unable to determine GitHub repository from PR URL: {url}")
    return f"{parts[0]}/{parts[1]}"


def _pull_number_from_url(url: str) -> int | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) >= 4 and parts[-2] == "pull":
        try:
            return int(parts[-1])
        except ValueError:
            return None
    return None


def _read_optional(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _relative_to(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _login(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("login", "") or "")
    return ""


def _check_passed(check: PrCheck) -> bool:
    bucket = check.bucket.lower()
    state = check.state.upper()
    if bucket in {"pass", "passing", "success", "skipping", "skip"}:
        return True
    return state in {"SUCCESS", "PASSED", "PASS", "SKIPPED", "NEUTRAL"}


def _check_required_action(check: PrCheck) -> str:
    bucket = check.bucket.lower()
    state = check.state.upper()
    if bucket in {"pending", "waiting"} or state in {"PENDING", "QUEUED", "IN_PROGRESS"}:
        return "Wait for this check to finish, then re-run PR monitoring."
    if bucket in {"fail", "failing", "failure"} or state in {"FAILURE", "ERROR", "FAILED"}:
        return "Inspect the failing check and fix the reported issue."
    if state in {"CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}:
        return "Restart or resolve the blocked check in GitHub."
    return "Inspect this check and resolve any blocking status."


def _check_by_name(checks: list[PrCheck], name: str) -> PrCheck | None:
    for check in checks:
        if check.name == name:
            return check
    return None


def _check_status(check: PrCheck | None) -> str:
    if check is None:
        return ""
    return check.state or check.bucket


def _should_emit_feedback(item: PrFeedbackItem, seen_feedback_keys: set[str]) -> bool:
    if item.key.startswith("review-summary:"):
        return True
    if item.source in {"ci", "mergeability", "review-decision"}:
        return True
    return item.key not in seen_feedback_keys


def _md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")
