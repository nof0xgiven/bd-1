import json
from pathlib import Path

import pytest

from bd1.errors import PrError
from bd1.pr import PrPublication, PrRunner
from bd1.subprocesses import CommandResult


class StrictFakeCommands:
    def __init__(self, responses):
        self.responses = list(responses)
        self.commands = []

    def __call__(self, command, cwd):
        command = list(command)
        self.commands.append((command, Path(cwd)))
        if not self.responses:
            raise AssertionError(f"Unexpected command: {command}")

        expected, response = self.responses.pop(0)
        assert command == expected

        if isinstance(response, BaseException):
            raise response
        if isinstance(response, CommandResult):
            return response
        return CommandResult(0, response, "", command)

    def assert_exhausted(self):
        assert self.responses == []


def _failed(command, stderr="failed", stdout="", exit_code=1):
    return CommandResult(exit_code, stdout, stderr, command)


def _worktree(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    completed = worktree / ".artifacts" / "completed" / "fix-bug.md"
    review = worktree / ".artifacts" / "reviews" / "fix-bug-1-pass.md"
    completed.parent.mkdir(parents=True)
    review.parent.mkdir(parents=True)
    completed.write_text("# Completed\n\nValidation passed.\n", encoding="utf-8")
    review.write_text("# Review\n\nPASS\n", encoding="utf-8")
    return worktree, completed, review


def _body_path(worktree):
    return worktree / ".artifacts" / "pr" / "body.md"


def _push(branch):
    return ["git", "push", "-u", "origin", branch]


def _list_prs(branch):
    return [
        "gh",
        "pr",
        "list",
        "--head",
        branch,
        "--state",
        "open",
        "--json",
        "number,url,title,headRefName,baseRefName,state",
    ]


def _create_pr(worktree, branch, base_branch="main", *, draft=False):
    command = [
        "gh",
        "pr",
        "create",
        "--title",
        "bd-1: Fix bug",
        "--body-file",
        str(_body_path(worktree)),
        "--head",
        branch,
    ]
    if base_branch:
        command.extend(["--base", base_branch])
    if draft:
        command.append("--draft")
    return command


def _edit_pr(worktree, number):
    return [
        "gh",
        "pr",
        "edit",
        str(number),
        "--title",
        "bd-1: Fix bug",
        "--body-file",
        str(_body_path(worktree)),
    ]


def _view_pr(number):
    return [
        "gh",
        "pr",
        "view",
        str(number),
        "--json",
        "number,url,state,mergeable,reviewDecision,reviews,headRefName,baseRefName",
    ]


def _checks(number):
    return [
        "gh",
        "pr",
        "checks",
        str(number),
        "--json",
        "name,state,bucket,link,description,startedAt,completedAt",
    ]


def _review_comments(number=12):
    return [
        "gh",
        "api",
        f"repos/acme/demo/pulls/{number}/comments",
        "--paginate",
        "--slurp",
    ]


def _issue_comments(number=12):
    return [
        "gh",
        "api",
        f"repos/acme/demo/issues/{number}/comments",
        "--paginate",
        "--slurp",
    ]


def _existing_pr(number=12):
    return json.dumps(
        [
            {
                "number": number,
                "url": f"https://github.com/acme/demo/pull/{number}",
                "state": "OPEN",
            }
        ]
    )


def _pr_details(number=12, *, mergeable="MERGEABLE", review_decision="", reviews=None):
    return json.dumps(
        {
            "number": number,
            "url": f"https://github.com/acme/demo/pull/{number}",
            "state": "OPEN",
            "mergeable": mergeable,
            "reviewDecision": review_decision,
            "reviews": reviews or [],
        }
    )


def _passing_checks():
    return json.dumps([{"name": "tests", "bucket": "pass", "state": "SUCCESS", "link": ""}])


def _publish(runner, worktree, completed, review, *, branch="bd-1/run-1", draft=False):
    return runner.publish_or_update(
        worktree=worktree,
        task="Fix bug",
        branch=branch,
        base_branch="main",
        run_id="run-1",
        base_commit="abc123",
        completed_path=completed,
        review_path=review,
        draft=draft,
    )


def _monitor(
    runner,
    worktree,
    publication,
    *,
    branch="bd-1/run-1",
    feedback_number=1,
    wait_seconds=0,
    seen_feedback_keys=None,
):
    return runner.monitor(
        worktree=worktree,
        task="Fix bug",
        task_slug="fix-bug",
        publication=publication,
        branch=branch,
        feedback_number=feedback_number,
        wait_seconds=wait_seconds,
        seen_feedback_keys=set(seen_feedback_keys or set()),
    )


def _publish_and_monitor(runner, worktree, completed, review, **kwargs):
    publish_kwargs = {key: kwargs[key] for key in ["branch", "draft"] if key in kwargs}
    publication = _publish(runner, worktree, completed, review, **publish_kwargs)
    return _monitor(runner, worktree, publication, **kwargs)


def test_pr_runner_creates_pr_when_branch_has_no_open_pr(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), "[]"),
            (_create_pr(worktree, "bd-1/run-1"), "https://github.com/acme/demo/pull/12\n"),
            (_list_prs("bd-1/run-1"), _existing_pr(12)),
            (_view_pr(12), _pr_details(12)),
            (_checks(12), _passing_checks()),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    result = _publish_and_monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        completed,
        review,
    )

    assert result.number == 12
    assert result.url == "https://github.com/acme/demo/pull/12"
    assert result.feedback == []
    assert result.artifact_path == ""
    assert Path(result.complete_artifact_path).exists()
    assert (worktree / ".artifacts" / "pr" / "body.md").exists()
    fake.assert_exhausted()


def test_pr_runner_updates_existing_pr_instead_of_creating_duplicate(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), _existing_pr(44)),
            (_edit_pr(worktree, 44), ""),
            (_view_pr(44), _pr_details(44)),
            (_checks(44), _passing_checks()),
            (_review_comments(44), "[]"),
            (_issue_comments(44), "[]"),
        ]
    )

    result = _publish_and_monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        completed,
        review,
    )

    commands = [command for command, _ in fake.commands]
    assert result.number == 44
    assert not any(command[:3] == ["gh", "pr", "create"] for command in commands)
    assert any(command[:3] == ["gh", "pr", "edit"] for command in commands)
    fake.assert_exhausted()


def test_pr_runner_writes_feedback_artifact_for_failed_checks(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), _existing_pr(12)),
            (_edit_pr(worktree, 12), ""),
            (_view_pr(12), _pr_details(12)),
            (
                _checks(12),
                CommandResult(
                    1,
                    json.dumps(
                        [
                            {
                                "name": "pytest",
                                "bucket": "fail",
                                "state": "FAILURE",
                                "link": "https://ci.example/fail",
                                "description": "tests failed",
                            }
                        ]
                    ),
                    "",
                    _checks(12),
                ),
            ),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    result = _publish_and_monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        completed,
        review,
        feedback_number=2,
    )

    feedback_path = Path(result.artifact_path)
    assert feedback_path == worktree / ".artifacts" / "pr" / "fix-bug-2.md"
    assert feedback_path.exists()
    text = feedback_path.read_text(encoding="utf-8")
    assert "| Check | Status | Failure | Required Action |" in text
    assert "|---|---|---|---|" in text
    assert "pytest" in text
    assert "tests failed" in text
    assert "Consolidated Resolve Prompt" in text
    assert result.complete_artifact_path == ""
    fake.assert_exhausted()


def test_pr_runner_writes_feedback_for_review_and_issue_comments(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), _existing_pr(12)),
            (_edit_pr(worktree, 12), ""),
            (_view_pr(12), _pr_details(12)),
            (_checks(12), _passing_checks()),
            (
                _review_comments(12),
                json.dumps(
                    [
                        {
                            "id": 101,
                            "body": "Agent prompt: fix the edge case",
                            "user": {"login": "coderabbitai"},
                            "path": "src/app.py",
                            "html_url": "https://github.com/acme/demo/pull/12#discussion_r101",
                            "created_at": "2026-06-09T00:00:00Z",
                            "updated_at": "2026-06-09T00:00:01Z",
                            "commit_id": "def456",
                        }
                    ]
                ),
            ),
            (
                _issue_comments(12),
                json.dumps(
                    [
                        {
                            "id": 202,
                            "body": "Please also update docs.",
                            "user": {"login": "reviewer"},
                            "html_url": "https://github.com/acme/demo/pull/12#issuecomment-202",
                        }
                    ]
                ),
            ),
        ]
    )

    result = _publish_and_monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        completed,
        review,
    )

    keys = [item.key for item in result.feedback]
    assert keys == ["review:101", "conversation:202"]
    text = Path(result.artifact_path).read_text(encoding="utf-8")
    assert "coderabbitai" in text
    assert "reviewer" in text
    assert "fix the edge case" in text
    assert "update docs" in text
    fake.assert_exhausted()


def test_pr_runner_raises_controlled_error_for_malformed_json(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), "not-json"),
        ]
    )

    with pytest.raises(PrError, match="Invalid JSON"):
        _publish(
            PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
            worktree,
            completed,
            review,
        )


def test_pr_runner_raises_controlled_error_for_missing_command(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), OSError("No such file or directory: 'git'")),
        ]
    )

    with pytest.raises(PrError, match="Unable to start command"):
        _publish(
            PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
            worktree,
            completed,
            review,
        )


def test_pr_runner_raises_controlled_error_for_git_push_failure(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    command = _push("bd-1/run-1")
    fake = StrictFakeCommands(
        [
            (command, _failed(command, stderr="fatal: push failed")),
        ]
    )

    with pytest.raises(PrError, match="git push failed"):
        _publish(
            PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
            worktree,
            completed,
            review,
        )


def test_pr_runner_raises_controlled_error_for_pr_create_failure(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    command = _create_pr(worktree, "bd-1/run-1")
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), "[]"),
            (command, _failed(command, stderr="authentication required")),
        ]
    )

    with pytest.raises(PrError, match="gh pr create failed"):
        _publish(
            PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
            worktree,
            completed,
            review,
        )


def test_pr_runner_raises_for_nonzero_checks_with_empty_stdout(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), _existing_pr(12)),
            (_edit_pr(worktree, 12), ""),
            (_view_pr(12), _pr_details(12)),
            (_checks(12), CommandResult(8, "", "checks pending", _checks(12))),
        ]
    )

    publication = _publish(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        completed,
        review,
    )

    with pytest.raises(PrError, match="gh pr checks returned no JSON"):
        _monitor(
            PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
            worktree,
            publication,
        )


def test_pr_runner_reports_pending_checks_as_feedback(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), _existing_pr(12)),
            (_edit_pr(worktree, 12), ""),
            (_view_pr(12), _pr_details(12)),
            (
                _checks(12),
                CommandResult(
                    8,
                    json.dumps(
                        [
                            {
                                "name": "deploy",
                                "bucket": "pending",
                                "state": "QUEUED",
                                "link": "https://ci.example/pending",
                                "description": "",
                            }
                        ]
                    ),
                    "",
                    _checks(12),
                ),
            ),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    result = _publish_and_monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        completed,
        review,
    )

    assert [item.key for item in result.feedback] == ["ci:deploy"]
    assert "wait" in result.feedback[0].required_action.lower()
    assert result.complete_artifact_path == ""
    fake.assert_exhausted()


def test_pr_runner_reports_changes_requested_review_body(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    reviews = [
        {
            "id": "R_123",
            "state": "CHANGES_REQUESTED",
            "body": "Please simplify the parser.",
            "author": {"login": "maintainer"},
            "url": "https://github.com/acme/demo/pull/12#pullrequestreview-123",
            "submittedAt": "2026-06-09T00:00:00Z",
            "commit": {"oid": "def456"},
        }
    ]
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), _existing_pr(12)),
            (_edit_pr(worktree, 12), ""),
            (_view_pr(12), _pr_details(12, reviews=reviews)),
            (_checks(12), _passing_checks()),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    result = _publish_and_monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        completed,
        review,
    )

    assert [item.key for item in result.feedback] == ["review-summary:R_123"]
    assert result.feedback[0].author == "maintainer"
    assert result.feedback[0].body == "Please simplify the parser."
    assert result.feedback[0].commit_id == "def456"
    fake.assert_exhausted()


def test_pr_runner_keeps_seen_changes_requested_review_body_blocking(tmp_path):
    worktree, _, _ = _worktree(tmp_path)
    reviews = [
        {
            "id": "R_123",
            "state": "CHANGES_REQUESTED",
            "body": "Please simplify the parser.",
            "author": {"login": "maintainer"},
            "url": "https://github.com/acme/demo/pull/12#pullrequestreview-123",
            "submittedAt": "2026-06-09T00:00:00Z",
            "commit": {"oid": "def456"},
        }
    ]
    fake = StrictFakeCommands(
        [
            (
                _view_pr(12),
                _pr_details(12, review_decision="CHANGES_REQUESTED", reviews=reviews),
            ),
            (_checks(12), _passing_checks()),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    result = _monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        PrPublication(number=12, url="https://github.com/acme/demo/pull/12", state="OPEN"),
        seen_feedback_keys={"review-summary:R_123"},
    )

    assert [item.key for item in result.feedback] == ["review-summary:R_123"]
    assert result.feedback[0].body == "Please simplify the parser."
    assert Path(result.artifact_path).exists()
    assert result.complete_artifact_path == ""
    fake.assert_exhausted()


def test_pr_runner_keeps_seen_individual_changes_requested_review_blocking(tmp_path):
    worktree, _, _ = _worktree(tmp_path)
    reviews = [
        {
            "id": "r1",
            "state": "CHANGES_REQUESTED",
            "body": "Please handle the edge case.",
            "author": {"login": "maintainer"},
            "url": "https://github.com/acme/demo/pull/12#pullrequestreview-r1",
            "submittedAt": "2026-06-09T00:00:00Z",
        }
    ]
    fake = StrictFakeCommands(
        [
            (_view_pr(12), _pr_details(12, reviews=reviews)),
            (_checks(12), _passing_checks()),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    result = _monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        PrPublication(number=12, url="https://github.com/acme/demo/pull/12", state="OPEN"),
        seen_feedback_keys={"review-summary:r1"},
    )

    assert [item.key for item in result.feedback] == ["review-summary:r1"]
    assert result.feedback[0].body == "Please handle the edge case."
    assert Path(result.artifact_path).exists()
    assert result.complete_artifact_path == ""
    fake.assert_exhausted()


def test_pr_runner_filters_seen_feedback_keys(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), _existing_pr(12)),
            (_edit_pr(worktree, 12), ""),
            (_view_pr(12), _pr_details(12)),
            (_checks(12), _passing_checks()),
            (
                _review_comments(12),
                json.dumps(
                    [
                        {
                            "id": 101,
                            "body": "Already handled.",
                            "user": {"login": "coderabbitai"},
                            "html_url": "https://github.com/acme/demo/pull/12#discussion_r101",
                        }
                    ]
                ),
            ),
            (
                _issue_comments(12),
                json.dumps(
                    [
                        {
                            "id": 202,
                            "body": "Already handled too.",
                            "user": {"login": "reviewer"},
                            "html_url": "https://github.com/acme/demo/pull/12#issuecomment-202",
                        }
                    ]
                ),
            ),
        ]
    )

    result = _publish_and_monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        completed,
        review,
        seen_feedback_keys={"review:101", "conversation:202"},
    )

    assert result.feedback == []
    assert result.artifact_path == ""
    assert Path(result.complete_artifact_path).exists()
    fake.assert_exhausted()


def test_pr_runner_keeps_seen_ci_failure_visible_while_still_failing(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), _existing_pr(12)),
            (_edit_pr(worktree, 12), ""),
            (_view_pr(12), _pr_details(12)),
            (
                _checks(12),
                CommandResult(
                    1,
                    json.dumps(
                        [
                            {
                                "name": "pytest",
                                "bucket": "fail",
                                "state": "FAILURE",
                                "link": "https://ci.example/fail",
                                "description": "tests still failed",
                            }
                        ]
                    ),
                    "",
                    _checks(12),
                ),
            ),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    result = _publish_and_monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        completed,
        review,
        seen_feedback_keys={"ci:pytest"},
    )

    assert [item.key for item in result.feedback] == ["ci:pytest"]
    assert Path(result.artifact_path).exists()
    assert result.complete_artifact_path == ""
    fake.assert_exhausted()


def test_pr_runner_keeps_seen_mergeability_blocker_visible_while_still_blocking(tmp_path):
    worktree, _, _ = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_view_pr(12), _pr_details(12, mergeable="CONFLICTING")),
            (_checks(12), _passing_checks()),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    result = _monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        PrPublication(number=12, url="https://github.com/acme/demo/pull/12", state="OPEN"),
        seen_feedback_keys={"mergeability:CONFLICTING"},
    )

    assert result.merge_conflict is True
    assert [item.key for item in result.feedback] == ["mergeability:CONFLICTING"]
    assert Path(result.artifact_path).exists()
    assert result.complete_artifact_path == ""
    fake.assert_exhausted()


def test_pr_runner_reports_changes_requested_review_decision_without_review_body(tmp_path):
    worktree, _, _ = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_view_pr(12), _pr_details(12, review_decision="CHANGES_REQUESTED")),
            (_checks(12), _passing_checks()),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    result = _monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        PrPublication(number=12, url="https://github.com/acme/demo/pull/12", state="OPEN"),
    )

    assert [item.key for item in result.feedback] == ["review-decision:CHANGES_REQUESTED"]
    assert result.feedback[0].source == "review-decision"
    assert "CHANGES_REQUESTED" in result.feedback[0].body
    assert result.complete_artifact_path == ""
    fake.assert_exhausted()


def test_pr_runner_flattens_slurped_nested_page_arrays(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), _existing_pr(12)),
            (_edit_pr(worktree, 12), ""),
            (_view_pr(12), _pr_details(12)),
            (_checks(12), _passing_checks()),
            (
                _review_comments(12),
                json.dumps(
                    [
                        [
                            {
                                "id": 101,
                                "body": "First page review comment.",
                                "user": {"login": "coderabbitai"},
                                "html_url": "https://github.com/acme/demo/pull/12#discussion_r101",
                            }
                        ],
                        [
                            {
                                "id": 102,
                                "body": "Second page review comment.",
                                "user": {"login": "coderabbitai"},
                                "html_url": "https://github.com/acme/demo/pull/12#discussion_r102",
                            }
                        ],
                    ]
                ),
            ),
            (
                _issue_comments(12),
                json.dumps(
                    [
                        [
                            {
                                "id": 203,
                                "body": "First page issue comment.",
                                "user": {"login": "reviewer"},
                                "html_url": "https://github.com/acme/demo/pull/12#issuecomment-203",
                            }
                        ],
                        [
                            {
                                "id": 204,
                                "body": "Second page issue comment.",
                                "user": {"login": "reviewer"},
                                "html_url": "https://github.com/acme/demo/pull/12#issuecomment-204",
                            }
                        ],
                    ]
                ),
            ),
        ]
    )

    result = _publish_and_monitor(
        PrRunner(pr_command="gh", command_runner=fake, sleeper=lambda _: None),
        worktree,
        completed,
        review,
    )

    assert [item.key for item in result.feedback] == [
        "review:101",
        "review:102",
        "conversation:203",
        "conversation:204",
    ]
    text = Path(result.artifact_path).read_text(encoding="utf-8")
    assert "First page review comment." in text
    assert "Second page review comment." in text
    assert "First page issue comment." in text
    assert "Second page issue comment." in text
    fake.assert_exhausted()


def test_pr_runner_distinguishes_conflict_from_unknown_mergeability(tmp_path):
    worktree, completed, review = _worktree(tmp_path)
    fake_conflict = StrictFakeCommands(
        [
            (_push("bd-1/run-1"), ""),
            (_list_prs("bd-1/run-1"), _existing_pr(12)),
            (_edit_pr(worktree, 12), ""),
            (_view_pr(12), _pr_details(12, mergeable="CONFLICTING")),
            (_checks(12), _passing_checks()),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    conflict = _publish_and_monitor(
        PrRunner(pr_command="gh", command_runner=fake_conflict, sleeper=lambda _: None),
        worktree,
        completed,
        review,
    )

    assert conflict.merge_conflict is True
    assert [item.key for item in conflict.feedback] == ["mergeability:CONFLICTING"]

    fake_unknown = StrictFakeCommands(
        [
            (_view_pr(12), _pr_details(12, mergeable="UNKNOWN")),
            (_checks(12), _passing_checks()),
            (_review_comments(12), "[]"),
            (_issue_comments(12), "[]"),
        ]
    )

    unknown = _monitor(
        PrRunner(pr_command="gh", command_runner=fake_unknown, sleeper=lambda _: None),
        worktree,
        PrPublication(number=12, url="https://github.com/acme/demo/pull/12", state="OPEN"),
    )

    assert unknown.merge_conflict is False
    assert [item.key for item in unknown.feedback] == ["mergeability:UNKNOWN"]
    fake_conflict.assert_exhausted()
    fake_unknown.assert_exhausted()
