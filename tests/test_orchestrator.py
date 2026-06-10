import json
import shlex
import subprocess
from pathlib import Path

import pytest

from bd1.config import default_workspace_config
from bd1.errors import DirtyRepositoryError, PrError
from bd1.git import get_status_porcelain
from bd1.models import RunState
from bd1.orchestrator import Orchestrator, compile_execution_prompt
from bd1.pr import PrCheck, PrFeedbackItem, PrResult
from bd1.run_index import RunIndex
from tests.fakes import (
    FakePiBehavior,
    FakePiRunner,
    FakePrRunner,
    FakeReasoning,
    FakeSetupRunner,
    FakeVetRunner,
    hermetic_git_env,
)


def make_config(repo: Path, *, max_attempts: int = 5, setup_script: str = ""):
    config = default_workspace_config("demo", str(repo), "Demo product", setup_script, "main")
    return config.__class__.from_dict({**config.to_dict(), "max_attempts": max_attempts})


def make_orchestrator(tmp_path, **overrides) -> Orchestrator:
    overrides.setdefault("reasoning", FakeReasoning(["PASS"]))
    overrides.setdefault("pr_runner", FakePrRunner())
    return Orchestrator(global_root=tmp_path / "global", **overrides)


def test_dirty_base_fails_before_worktree_creation(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    orchestrator = make_orchestrator(tmp_path)

    with pytest.raises(DirtyRepositoryError):
        orchestrator.run(make_config(repo), "Fix bug")

    assert not (tmp_path / "global" / "worktrees").exists()


def test_setup_failure_blocks_and_writes_setup_artifacts(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(tmp_path, setup_runner=FakeSetupRunner(exit_code=7))

    record = orchestrator.run(make_config(repo, setup_script="setup"), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert record.blocker_path
    assert (Path(record.worktree) / ".sessions" / record.run_id / "setup-stderr.txt").exists()


def test_execution_prompt_contains_executor_contract_clauses():
    prompt = compile_execution_prompt(
        task="Fix bug",
        discovery_context_path=".artifacts/context/fix.md",
        plan_path=".artifacts/plans/fix.md",
        workspace_root="/repo",
        worktree_root="/worktree",
        completion_summary_path=".artifacts/completed/fix.md",
    )

    for clause in [
        "Read `.artifacts/` documentation",
        "Work only in the task worktree",
        "write the smallest failing real test first",
        "Modify only files required",
        "Run focused tests and required quality gates",
        "Commit changes before exit",
        "Resolve pre-commit failures without workarounds or hacks",
        "Leave the worktree clean before exit",
        ".artifacts/completed/fix.md",
    ]:
        assert clause in prompt


def test_happy_path_persists_transitions_and_is_indexable(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    transitions = (
        Path(record.worktree) / ".sessions" / record.run_id / "transitions.jsonl"
    ).read_text(encoding="utf-8")
    for state in [
        "BASE_VERIFIED",
        "WORKTREE_CREATED",
        "DISCOVERY_COMPLETE",
        "PLAN_COMPLETE",
        "EXECUTION_PROMPT_READY",
        "EXECUTION_RUNNING",
        "EXECUTION_COMMITTED",
        "VET_PASSED",
        "REVIEW_PASSED",
        "COMPLETE",
    ]:
        assert state in transitions

    index = RunIndex(tmp_path / "runs.db")
    index.rebuild_from_workspace(Path(record.worktree))
    assert index.get_run(record.run_id) == record


def test_complete_run_leaves_task_worktree_clean_after_learning_capture(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")
    worktree = Path(record.worktree)

    assert record.state is RunState.COMPLETE
    store_root = tmp_path / "global" / "learning" / "demo"
    assert (store_root / "learning.jsonl").exists()
    assert list((store_root / "learnings").glob("*.json"))
    assert not (worktree / ".examples").exists()
    assert not (worktree / ".learning").exists()
    assert get_status_porcelain(worktree) == []


def test_learning_round_trip_into_next_run_discovery_evidence(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    first_reasoning = FakeReasoning(["PASS"])
    first = make_orchestrator(
        tmp_path,
        reasoning=first_reasoning,
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
    )
    first_record = first.run(make_config(repo), "Fix bug")
    assert first_record.state is RunState.COMPLETE

    store_root = tmp_path / "global" / "learning" / "demo"
    saved = list((store_root / "learnings").glob("*.json"))
    assert saved
    saved_payload = json.loads(saved[0].read_text(encoding="utf-8"))
    assert saved_payload["status"] == "active"
    assert saved_payload["source_run_id"] == first_record.run_id

    second_reasoning = FakeReasoning(["PASS"])
    second = make_orchestrator(
        tmp_path,
        reasoning=second_reasoning,
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
    )
    second_record = second.run(make_config(repo), "Improve docs")

    assert second_record.state is RunState.COMPLETE
    discovery_evidence = second_reasoning.discover_evidence[0]
    assert "Fake learning from task: Fix bug" in discovery_evidence.relevant_learnings


def test_learning_extractor_receives_diff_review_history_and_pr_feedback(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    feedback_result = PrResult(
        number=5,
        url="https://github.com/acme/demo/pull/5",
        state="OPEN",
        checks=[PrCheck("tests", "fail", "FAILURE", "", "failed")],
        feedback=[
            PrFeedbackItem(
                key="ci:tests",
                source="ci",
                author="github",
                body="failed",
                path="tests",
                url="",
                required_action="Fix tests.",
            )
        ],
        merge_conflict=False,
        artifact_path=".artifacts/pr/fix-bug-1.md",
    )
    complete_result = PrResult(
        number=5,
        url="https://github.com/acme/demo/pull/5",
        state="OPEN",
        checks=[],
        feedback=[],
        merge_conflict=False,
        complete_artifact_path=".artifacts/pr/fix-bug-2-complete.md",
    )
    reasoning = FakeReasoning(["FAIL", "PASS", "PASS"])
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=reasoning,
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([10, 0, 0, 0]),
        pr_runner=FakePrRunner([feedback_result, complete_result]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    events = {call["review_markdown"].splitlines()[0]: call for call in reasoning.learn_calls}

    vet_call = events["vet findings"]
    assert "goal_mismatch: Wrong goal" in vet_call["review_markdown"]
    assert vet_call["final_diff"].startswith("diff --git") or "change.txt" in vet_call["final_diff"]

    review_call = events["review failed"]
    assert "Verdict: FAIL" in review_call["review_markdown"]
    assert "change.txt" in review_call["final_diff"]

    pr_call = events["pr feedback"]
    assert "Resolve PR feedback" in pr_call["pr_feedback"]

    pass_call = events["pass"]
    assert "Verdict: PASS" in pass_call["review_markdown"]
    assert "change.txt" in pass_call["final_diff"]
    assert "Resolve PR feedback" in pass_call["pr_feedback"]


def test_vet_history_loader_command_quotes_session_path(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    vet = FakeVetRunner([0])
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=vet,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    command = vet.history_loader_commands[0]
    assert command.startswith("bd1-pi-history-loader ")
    quoted_path = command.removeprefix("bd1-pi-history-loader ")
    assert shlex.split(quoted_path) == [record.attempts[0].pi_session_file]


def test_dirty_worktree_resumes_same_session_with_exact_prompt(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    pi = FakePiRunner(
        [
            FakePiBehavior(create_session=True, commit=False, dirty=True),
            FakePiBehavior(create_session=True, commit=True, dirty=False),
        ]
    )
    orchestrator = make_orchestrator(tmp_path, pi_runner=pi, vet_runner=FakeVetRunner([0]))

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    assert pi.prompts[1] == "commit and resolve before exit"
    assert pi.session_ids[0] == pi.session_ids[1]


def test_missing_pi_session_blocks_before_vet(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    vet = FakeVetRunner([0])
    orchestrator = make_orchestrator(
        tmp_path,
        pi_runner=FakePiRunner([FakePiBehavior(create_session=False, commit=True)]),
        vet_runner=vet,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert vet.calls == 0
    assert "No Pi session JSONL" in Path(record.blocker_path).read_text(encoding="utf-8")


def test_pi_nonzero_exit_with_session_blocks_before_vet_and_pr(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    vet = FakeVetRunner([0])
    pr = FakePrRunner()
    orchestrator = make_orchestrator(
        tmp_path,
        pi_runner=FakePiRunner(
            [
                FakePiBehavior(
                    create_session=True,
                    commit=True,
                    exit_code=7,
                    stderr="pi crashed after writing session",
                )
            ]
        ),
        vet_runner=vet,
        pr_runner=pr,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert vet.calls == 0
    assert pr.publish_calls == []
    blocker = Path(record.blocker_path).read_text(encoding="utf-8")
    assert "Pi failed" in blocker
    assert "exit 7" in blocker
    assert "pi crashed after writing session" in blocker


def test_dirty_worktree_cleanup_pi_nonzero_exit_blocks_before_vet_and_pr(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    vet = FakeVetRunner([0])
    pr = FakePrRunner()
    orchestrator = make_orchestrator(
        tmp_path,
        pi_runner=FakePiRunner(
            [
                FakePiBehavior(create_session=True, commit=False, dirty=True),
                FakePiBehavior(
                    create_session=True,
                    commit=True,
                    exit_code=7,
                    stderr="cleanup pi failed",
                ),
            ]
        ),
        vet_runner=vet,
        pr_runner=pr,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert vet.calls == 0
    assert pr.publish_calls == []
    blocker = Path(record.blocker_path).read_text(encoding="utf-8")
    assert "Pi failed" in blocker
    assert "exit 7" in blocker
    assert "cleanup pi failed" in blocker


def test_pi_success_without_commits_blocks_before_vet_and_pr(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    vet = FakeVetRunner([0])
    pr = FakePrRunner()
    orchestrator = make_orchestrator(
        tmp_path,
        pi_runner=FakePiRunner([FakePiBehavior(make_changes=False)]),
        vet_runner=vet,
        pr_runner=pr,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert vet.calls == 0
    assert pr.publish_calls == []
    blocker = Path(record.blocker_path).read_text(encoding="utf-8")
    assert "Pi made no changes" in blocker
    assert "Pi completed without committing any changes" in blocker
    transitions = (
        Path(record.worktree) / ".sessions" / record.run_id / "transitions.jsonl"
    ).read_text(encoding="utf-8")
    assert "EXECUTION_COMMITTED" not in transitions


def test_fake_pi_no_changes_behavior_leaves_worktree_at_base(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    pi = FakePiRunner([FakePiBehavior(make_changes=False)])
    orchestrator = make_orchestrator(tmp_path, pi_runner=pi, vet_runner=FakeVetRunner([0]))

    record = orchestrator.run(make_config(repo), "Fix bug")

    worktree = Path(record.worktree)
    assert not (worktree / "change.txt").exists()
    assert get_status_porcelain(worktree) == []
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree,
        capture_output=True,
        text=True,
        check=True,
        env=hermetic_git_env(),
    ).stdout.strip()
    assert head == record.base_commit


def test_pi_still_dirty_after_clean_commit_retry_blocks_before_vet_and_pr(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    vet = FakeVetRunner([0])
    pr = FakePrRunner()
    pi = FakePiRunner(
        [
            FakePiBehavior(create_session=True, commit=False, dirty=True),
            FakePiBehavior(create_session=True, commit=False, dirty=True),
        ]
    )
    orchestrator = make_orchestrator(tmp_path, pi_runner=pi, vet_runner=vet, pr_runner=pr)

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert len(pi.prompts) == 2
    assert pi.prompts[1] == "commit and resolve before exit"
    assert vet.calls == 0
    assert pr.publish_calls == []
    blocker = Path(record.blocker_path).read_text(encoding="utf-8")
    assert "Dirty worktree" in blocker
    assert "Pi exited with uncommitted changes after clean-commit prompt." in blocker


def test_clean_commit_retry_missing_session_blocks_before_vet_and_pr(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    vet = FakeVetRunner([0])
    pr = FakePrRunner()
    pi = FakePiRunner(
        [
            FakePiBehavior(create_session=True, commit=False, dirty=True),
            FakePiBehavior(create_session=False),
        ]
    )
    orchestrator = make_orchestrator(tmp_path, pi_runner=pi, vet_runner=vet, pr_runner=pr)

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert len(pi.prompts) == 2
    assert vet.calls == 0
    assert pr.publish_calls == []
    blocker = Path(record.blocker_path).read_text(encoding="utf-8")
    assert "Pi session missing" in blocker
    assert "No Pi session JSONL" in blocker


def test_fake_pi_runner_coerces_zero_exit_to_two_when_session_missing(tmp_path, init_git_repo):
    worktree = init_git_repo(tmp_path / "fake-worktree")
    pi = FakePiRunner([FakePiBehavior(create_session=False, exit_code=0)])
    result = pi.run(
        worktree=worktree,
        prompt="Fix bug",
        session_id="session-1",
        session_dir=tmp_path / "pi-session",
        artifact_dir=tmp_path / "artifacts",
    )

    assert result.session_file is None
    assert result.exit_code == 2


def test_vet_findings_loop_review_failure_loop_and_learning_events(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    reasoning = FakeReasoning(["FAIL", "PASS"])
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=reasoning,
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([10, 0, 0]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    assert len(record.attempts) == 3
    assert any("vet findings" in event for event in reasoning.learn_events)
    assert any("review failed" in event for event in reasoning.learn_events)
    assert any("pass" in event for event in reasoning.learn_events)


@pytest.mark.parametrize("exit_code", [1, 2])
def test_vet_runtime_and_config_errors_block(tmp_path, init_git_repo, exit_code):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([exit_code]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert "Vet failed" in Path(record.blocker_path).read_text(encoding="utf-8")


def test_vet_unknown_nonzero_exit_blocks_before_review_and_pr(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    reasoning = FakeReasoning(["PASS"])
    pr = FakePrRunner()
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=reasoning,
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([127]),
        pr_runner=pr,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert reasoning.review_calls == 0
    assert pr.publish_calls == []
    blocker = Path(record.blocker_path).read_text(encoding="utf-8")
    assert "Vet failed" in blocker
    assert "exit 127" in blocker
    assert "vet stderr" in blocker


def test_repeated_vet_findings_max_attempts_writes_blocker(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([10, 10, 10]),
    )

    record = orchestrator.run(make_config(repo, max_attempts=2), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert "Max attempts reached" in Path(record.blocker_path).read_text(encoding="utf-8")
    assert json.loads(
        (Path(record.worktree) / ".sessions" / record.run_id / "run-record.json").read_text()
    )


def test_review_pass_publishes_and_monitors_pr_before_complete(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    pr = FakePrRunner()
    config = make_config(repo).__class__.from_dict(
        {**make_config(repo).to_dict(), "pr_base_branch": "release", "pr_draft": True}
    )
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
        pr_runner=pr,
    )

    record = orchestrator.run(config, "Fix bug")

    assert record.state is RunState.COMPLETE
    assert record.final_verdict == "PASS"
    assert record.pr_number == 1
    assert record.pr_url == "https://github.com/acme/demo/pull/1"
    assert record.pr_complete_path.endswith("fix-bug-1-complete.md")
    transitions = (
        Path(record.worktree) / ".sessions" / record.run_id / "transitions.jsonl"
    ).read_text(encoding="utf-8")
    for state in [
        "REVIEW_PASSED",
        "PR_PUBLISHING",
        "PR_CREATED",
        "PR_MONITORING",
        "PR_READY",
        "COMPLETE",
    ]:
        assert state in transitions
    assert pr.publish_calls[0]["worktree"] == Path(record.worktree)
    assert pr.publish_calls[0]["task"] == "Fix bug"
    assert pr.publish_calls[0]["branch"] == record.branch
    assert pr.publish_calls[0]["base_branch"] == "release"
    assert pr.publish_calls[0]["run_id"] == record.run_id
    assert pr.publish_calls[0]["base_commit"] == record.base_commit
    assert pr.publish_calls[0]["completed_path"] == Path(record.artifacts["completed"])
    assert pr.publish_calls[0]["review_path"] == Path(record.attempts[-1].review_path)
    assert pr.publish_calls[0]["draft"] is True
    assert pr.monitor_calls[0]["publication"].number == 1
    assert pr.monitor_calls[0]["task_slug"] == "fix-bug"
    assert pr.monitor_calls[0]["branch"] == record.branch
    assert pr.monitor_calls[0]["feedback_number"] == 1
    assert pr.monitor_calls[0]["wait_seconds"] == 600
    assert pr.monitor_calls[0]["seen_feedback_keys"] == set()
    assert pr.monitor_calls[0]["max_polls"] == 6


def test_pr_merged_completes_run_and_records_pr_merged_learning(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    merged_result = PrResult(
        number=5,
        url="https://github.com/acme/demo/pull/5",
        state="MERGED",
        checks=[],
        feedback=[],
        merge_conflict=False,
        complete_artifact_path=".artifacts/pr/fix-bug-1-complete.md",
    )
    pr = FakePrRunner([merged_result])
    reasoning = FakeReasoning(["PASS"])
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=reasoning,
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
        pr_runner=pr,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    assert record.final_verdict == "PASS"
    assert any(event.startswith("pr merged") for event in reasoning.learn_events)
    transitions = (
        Path(record.worktree) / ".sessions" / record.run_id / "transitions.jsonl"
    ).read_text(encoding="utf-8")
    assert "PR merged" in transitions
    assert "COMPLETE" in transitions


def test_pr_closed_blocks_without_creating_replacement_pr(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    closed_result = PrResult(
        number=5,
        url="https://github.com/acme/demo/pull/5",
        state="CLOSED",
        checks=[],
        feedback=[],
        merge_conflict=False,
    )
    pr = FakePrRunner([closed_result])
    pi = FakePiRunner()
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=pi,
        vet_runner=FakeVetRunner([0]),
        pr_runner=pr,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    blocker = Path(record.blocker_path).read_text(encoding="utf-8")
    assert "PR closed" in blocker
    assert "closed without merging" in blocker
    assert len(pr.publish_calls) == 1
    assert len(pi.prompts) == 1


def test_pr_unsettled_checks_block_instead_of_reprompting_pi(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    unsettled_result = PrResult(
        number=5,
        url="https://github.com/acme/demo/pull/5",
        state="OPEN",
        checks=[PrCheck("deploy", "pending", "QUEUED", "", "")],
        feedback=[],
        merge_conflict=False,
        unsettled=True,
    )
    pr = FakePrRunner([unsettled_result])
    pi = FakePiRunner()
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=pi,
        vet_runner=FakeVetRunner([0]),
        pr_runner=pr,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    blocker = Path(record.blocker_path).read_text(encoding="utf-8")
    assert "PR checks did not settle" in blocker
    assert len(pi.prompts) == 1


def test_pr_feedback_loops_back_to_pi_prompt_and_then_completes(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    feedback_result = PrResult(
        number=2,
        url="https://github.com/acme/demo/pull/2",
        state="OPEN",
        checks=[PrCheck("tests", "fail", "FAILURE", "", "failed")],
        feedback=[
            PrFeedbackItem(
                key="ci:tests",
                source="ci",
                author="github",
                body="failed",
                path="tests",
                url="",
                required_action="Fix tests.",
            )
        ],
        merge_conflict=False,
        artifact_path=".artifacts/pr/fix-bug-1.md",
    )
    complete_result = PrResult(
        number=2,
        url="https://github.com/acme/demo/pull/2",
        state="OPEN",
        checks=[PrCheck("tests", "pass", "SUCCESS", "", "")],
        feedback=[],
        merge_conflict=False,
        complete_artifact_path=".artifacts/pr/fix-bug-2-complete.md",
    )
    pi = FakePiRunner()
    pr = FakePrRunner([feedback_result, complete_result])
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS", "PASS"]),
        pi_runner=pi,
        vet_runner=FakeVetRunner([0, 0]),
        pr_runner=pr,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    assert len(record.attempts) == 2
    assert len(pr.publish_calls) == 2
    assert len(pr.monitor_calls) == 2
    assert record.pr_feedback_paths == [str(Path(record.worktree) / ".artifacts/pr/fix-bug-1.md")]
    assert record.pr_complete_path.endswith("fix-bug-2-complete.md")
    assert record.pr_seen_feedback_keys == ["ci:tests"]
    assert "Resolve PR feedback" in pi.prompts[1]


def test_pr_feedback_max_attempts_blocks(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    feedback_result = PrResult(
        number=3,
        url="https://github.com/acme/demo/pull/3",
        state="OPEN",
        checks=[PrCheck("tests", "fail", "FAILURE", "", "failed")],
        feedback=[
            PrFeedbackItem(
                key="ci:tests",
                source="ci",
                author="github",
                body="failed",
                path="tests",
                url="",
                required_action="Fix tests.",
            ),
        ],
        merge_conflict=False,
        artifact_path=".artifacts/pr/fix-bug-1.md",
    )
    pr = FakePrRunner([feedback_result, feedback_result])
    config = make_config(repo, max_attempts=5).__class__.from_dict(
        {**make_config(repo, max_attempts=5).to_dict(), "max_pr_feedback_attempts": 1}
    )
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS", "PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0, 0]),
        pr_runner=pr,
    )

    record = orchestrator.run(config, "Fix bug")

    assert record.state is RunState.BLOCKED
    assert "Max PR feedback attempts reached" in Path(record.blocker_path).read_text(
        encoding="utf-8"
    )


def test_pr_seen_feedback_keys_pass_into_monitor_and_update_from_feedback(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    feedback_result = PrResult(
        number=4,
        url="https://github.com/acme/demo/pull/4",
        state="OPEN",
        checks=[],
        feedback=[
            PrFeedbackItem(
                key="review:1",
                source="review",
                author="reviewer",
                body="Please adjust this.",
                path="src/app.py",
                url="https://github.com/acme/demo/pull/4#discussion_r1",
                required_action="Address review comment.",
            )
        ],
        merge_conflict=False,
        artifact_path=".artifacts/pr/fix-bug-1.md",
    )
    complete_result = PrResult(
        number=4,
        url="https://github.com/acme/demo/pull/4",
        state="OPEN",
        checks=[],
        feedback=[],
        merge_conflict=False,
        complete_artifact_path=".artifacts/pr/fix-bug-2-complete.md",
    )
    pr = FakePrRunner([feedback_result, complete_result])
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS", "PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0, 0]),
        pr_runner=pr,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert pr.monitor_calls[0]["seen_feedback_keys"] == set()
    assert pr.monitor_calls[1]["seen_feedback_keys"] == {"review:1"}
    assert record.pr_seen_feedback_keys == ["review:1"]


@pytest.mark.parametrize(
    ("phase", "expected_title"),
    [
        ("publish", "PR failed"),
        ("monitor", "PR monitoring failed"),
    ],
)
def test_pr_publishing_or_monitoring_bd1_error_blocks_cleanly(
    tmp_path, init_git_repo, phase, expected_title
):
    repo = init_git_repo(tmp_path / "repo")
    error = PrError(f"{phase} exploded")
    pr = (
        FakePrRunner(publish_error=error)
        if phase == "publish"
        else FakePrRunner(monitor_error=error)
    )
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
        pr_runner=pr,
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    blocker = Path(record.blocker_path).read_text(encoding="utf-8")
    assert expected_title in blocker
    assert f"{phase} exploded" in blocker


class ExplodingDiscoveryReasoning(FakeReasoning):
    def discover(self, evidence):
        raise RuntimeError("LM exploded mid-discovery")


class ExplodingLearnReasoning(FakeReasoning):
    def learn(self, evidence, *, review_markdown: str, final_diff: str = "", pr_feedback: str = ""):
        raise RuntimeError("learning LM unavailable")


def test_unexpected_exception_lands_run_in_blocked(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=ExplodingDiscoveryReasoning(),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert record.final_verdict == "BLOCKED"
    blocker = Path(record.blocker_path).read_text(encoding="utf-8")
    assert "Unexpected error: RuntimeError" in blocker
    assert "LM exploded mid-discovery" in blocker
    assert "Traceback" in blocker
    persisted = json.loads(
        (Path(record.worktree) / ".sessions" / record.run_id / "run-record.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["state"] == "BLOCKED"


def test_unexpected_pr_runner_exception_lands_run_in_blocked(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
        pr_runner=FakePrRunner(publish_error=RuntimeError("gh binary vanished")),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert "gh binary vanished" in Path(record.blocker_path).read_text(encoding="utf-8")


def test_complete_transition_happens_even_when_learning_fails(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=ExplodingLearnReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    assert record.final_verdict == "PASS"
    transitions = (
        Path(record.worktree) / ".sessions" / record.run_id / "transitions.jsonl"
    ).read_text(encoding="utf-8")
    assert "COMPLETE" in transitions
    note = Path(record.worktree) / ".artifacts" / "learning" / f"{record.run_id}-pass-error.md"
    assert "Learning capture failed" in note.read_text(encoding="utf-8")


def test_blocked_transition_happens_even_when_learning_fails(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=ExplodingLearnReasoning(["PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([1]),
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.BLOCKED
    assert record.final_verdict == "BLOCKED"
    transitions = (
        Path(record.worktree) / ".sessions" / record.run_id / "transitions.jsonl"
    ).read_text(encoding="utf-8")
    assert "BLOCKED" in transitions


def test_clean_commit_retry_preserves_original_pi_artifacts(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    reasoning = FakeReasoning(["PASS"])
    pi = FakePiRunner(
        [
            FakePiBehavior(create_session=True, commit=False, dirty=True),
            FakePiBehavior(create_session=True, commit=True, dirty=False),
        ]
    )
    orchestrator = make_orchestrator(
        tmp_path, reasoning=reasoning, pi_runner=pi, vet_runner=FakeVetRunner([0])
    )

    record = orchestrator.run(make_config(repo), "Fix bug")

    assert record.state is RunState.COMPLETE
    attempt_dir = Path(record.worktree) / ".sessions" / record.run_id / "attempt-1"
    assert (attempt_dir / "pi-stdout.txt").read_text(encoding="utf-8") == "pi call 0\n"
    assert (attempt_dir / "clean-commit" / "pi-stdout.txt").read_text(
        encoding="utf-8"
    ) == "pi call 1\n"
    assert reasoning.review_inputs[0]["pi_completion_summary"] == "pi call 0\n"
    assert record.attempts[0].pi_stdout_path == str(attempt_dir / "pi-stdout.txt")


def test_pr_feedback_rounds_do_not_consume_execution_attempts(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    feedback_result = PrResult(
        number=9,
        url="https://github.com/acme/demo/pull/9",
        state="OPEN",
        checks=[PrCheck("tests", "fail", "FAILURE", "", "failed")],
        feedback=[
            PrFeedbackItem(
                key="ci:tests",
                source="ci",
                author="github",
                body="failed",
                path="tests",
                url="",
                required_action="Fix tests.",
            )
        ],
        merge_conflict=False,
        artifact_path=".artifacts/pr/fix-bug-1.md",
    )
    complete_result = PrResult(
        number=9,
        url="https://github.com/acme/demo/pull/9",
        state="OPEN",
        checks=[PrCheck("tests", "pass", "SUCCESS", "", "")],
        feedback=[],
        merge_conflict=False,
        complete_artifact_path=".artifacts/pr/fix-bug-2-complete.md",
    )
    orchestrator = make_orchestrator(
        tmp_path,
        reasoning=FakeReasoning(["PASS", "PASS"]),
        pi_runner=FakePiRunner(),
        vet_runner=FakeVetRunner([0, 0]),
        pr_runner=FakePrRunner([feedback_result, complete_result]),
    )

    record = orchestrator.run(make_config(repo, max_attempts=1), "Fix bug")

    assert record.state is RunState.COMPLETE
    assert len(record.attempts) == 2
