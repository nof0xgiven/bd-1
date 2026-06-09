import inspect

from bd1.dspy_programs import (
    CreateImplementationPlan,
    DecideReviewOutcome,
    DiscoverTaskContext,
    DspyReasoningPrograms,
    ExtractLearning,
    ReviewOutput,
    TemplateReasoningPrograms,
)
from bd1.evidence import EvidencePackage


def test_template_reasoning_is_test_only_fallback():
    evidence = EvidencePackage("Fix bug", "/repo", "README.md", "# Rules", "", "")

    output = TemplateReasoningPrograms().discover(evidence)

    assert "# Context Package" in output.markdown
    assert "Fix bug" in output.markdown


def test_review_output_normalizes_non_pass_verdicts_to_fail():
    assert ReviewOutput("PASS", "No issues.").verdict == "PASS"
    assert ReviewOutput("pass", "No issues.").verdict == "PASS"
    assert ReviewOutput("NEEDS_WORK", "Issue found.").verdict == "FAIL"
    assert ReviewOutput("", "Issue found.").verdict == "FAIL"


def test_review_interface_accepts_full_execution_evidence_without_live_model_calls():
    review_signature = inspect.signature(TemplateReasoningPrograms.review)

    for parameter in [
        "task",
        "discovery_context",
        "implementation_plan",
        "pi_completion_summary",
        "command_output_summary",
        "git_diff",
        "vet_json",
        "workspace_artifacts",
    ]:
        assert parameter in review_signature.parameters

    output = TemplateReasoningPrograms().review(
        task="Fix bug",
        discovery_context="Discovery notes",
        implementation_plan="Plan notes",
        pi_completion_summary="Pi says complete",
        command_output_summary="pytest passed",
        git_diff="diff --git a/app.py b/app.py",
        vet_json='{"findings": []}',
        workspace_artifacts="# Rules",
    )

    assert output.verdict == "PASS"
    assert "Pi says complete" in output.markdown
    assert "diff --git" in output.markdown


def test_dspy_live_programs_use_documented_signatures_without_model_calls():
    programs = DspyReasoningPrograms()

    assert programs is not None
    assert {
        "task",
        "workspace_artifacts",
        "repo_evidence",
        "relevant_learnings",
        "external_examples",
    }.issubset(DiscoverTaskContext.__annotations__)
    assert {
        "task",
        "context_package",
        "workspace_rules",
        "relevant_learnings",
    }.issubset(CreateImplementationPlan.__annotations__)
    assert {
        "task",
        "implementation_plan",
        "coder_summary",
        "git_diff",
        "test_output",
        "vet_interpretation",
        "workspace_artifacts",
    }.issubset(DecideReviewOutcome.__annotations__)
    assert {
        "run_record",
        "final_diff",
        "pr_feedback",
        "review_history",
    }.issubset(ExtractLearning.__annotations__)


def test_learning_interface_accepts_diff_and_feedback_without_live_model_calls():
    evidence = EvidencePackage("Fix bug", "/repo", "README.md", "# Rules", "", "")
    learning_signature = inspect.signature(TemplateReasoningPrograms.learn)

    assert "final_diff" in learning_signature.parameters
    assert "pr_feedback" in learning_signature.parameters

    output = TemplateReasoningPrograms().learn(
        evidence,
        review_markdown="Review notes",
        final_diff="diff --git a/app.py b/app.py",
        pr_feedback="Please cover edge cases.",
    )

    assert "diff --git" in output.markdown
    assert "Please cover edge cases." in output.markdown
