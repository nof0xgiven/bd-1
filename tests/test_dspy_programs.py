import inspect
from types import SimpleNamespace

import pytest

from bd1.dspy_programs import (
    CreateImplementationPlan,
    DecideReviewOutcome,
    DiscoverTaskContext,
    DspyReasoningPrograms,
    ExtractLearning,
    ReviewOutput,
    TemplateReasoningPrograms,
    normalize_review_verdict,
)
from bd1.errors import ReasoningOutputError
from bd1.evidence import EvidencePackage


def test_template_reasoning_is_test_only_fallback():
    evidence = EvidencePackage("Fix bug", "/repo", "README.md", "# Rules", "", "")

    output = TemplateReasoningPrograms().discover(evidence)

    assert "# Context Package" in output.markdown
    assert "Fix bug" in output.markdown


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PASS", "PASS"),
        ("pass", "PASS"),
        ("**PASS**", "PASS"),
        ("PASS - safe to merge", "PASS"),
        ("Verdict: PASS.", "PASS"),
        ("FAIL", "FAIL"),
        ("**FAIL**", "FAIL"),
        ("REVISE", "FAIL"),
        ("NEEDS_WORK", "FAIL"),
        ("", "FAIL"),
        ("garbage output with no verdict", "FAIL"),
    ],
)
def test_review_verdict_is_binary_and_fails_closed(raw, expected):
    assert normalize_review_verdict(raw) == expected
    assert ReviewOutput(raw, "Review body.").verdict == expected


def test_review_output_preserves_raw_verdict_for_artifacts():
    output = ReviewOutput("**PASS** - safe to merge", "Review body.")

    assert output.verdict == "PASS"
    assert output.raw_verdict == "**PASS** - safe to merge"


def test_review_signature_is_binary_without_revision_prompt():
    assert "revision_prompt" not in DecideReviewOutcome.__annotations__
    assert "PASS | FAIL" in DecideReviewOutcome.output_fields["verdict"].json_schema_extra["desc"]


def test_signature_docstrings_encode_original_doctrines():
    assert "binary" in DecideReviewOutcome.__doc__.lower()
    assert "production" in DecideReviewOutcome.__doc__.lower()
    assert "mock" in DecideReviewOutcome.__doc__.lower()
    assert "ambigu" in DiscoverTaskContext.__doc__.lower()
    assert "source of truth" in DiscoverTaskContext.__doc__.lower()
    assert "current-state" in CreateImplementationPlan.__doc__.lower()
    assert "yagni" in CreateImplementationPlan.__doc__.lower()
    assert "easier" in ExtractLearning.__doc__.lower()


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


def _evidence() -> EvidencePackage:
    return EvidencePackage("Fix bug", "/repo", "README.md", "# Rules", "", "")


def _stub_program(prediction):
    def run(**kwargs):
        return prediction

    return run


def test_discover_raises_when_markdown_is_missing_or_empty():
    programs = DspyReasoningPrograms(discovery=_stub_program(SimpleNamespace()))
    with pytest.raises(ReasoningOutputError):
        programs.discover(_evidence())

    programs = DspyReasoningPrograms(
        discovery=_stub_program(SimpleNamespace(context_package_markdown=None))
    )
    with pytest.raises(ReasoningOutputError):
        programs.discover(_evidence())

    programs = DspyReasoningPrograms(
        discovery=_stub_program(SimpleNamespace(context_package_markdown="  "))
    )
    with pytest.raises(ReasoningOutputError):
        programs.discover(_evidence())


def test_plan_raises_when_markdown_is_missing():
    programs = DspyReasoningPrograms(planner=_stub_program(SimpleNamespace(plan_markdown=None)))
    with pytest.raises(ReasoningOutputError):
        programs.plan(_evidence(), discovery_context="ctx")


def test_review_raises_on_empty_markdown_and_defaults_missing_verdict_to_fail():
    programs = DspyReasoningPrograms(reviewer=_stub_program(SimpleNamespace(verdict="PASS")))
    with pytest.raises(ReasoningOutputError):
        programs.review(
            task="Fix bug",
            discovery_context="ctx",
            implementation_plan="plan",
            pi_completion_summary="done",
            command_output_summary="ok",
            git_diff="diff",
            vet_json="{}",
            workspace_artifacts="rules",
        )

    programs = DspyReasoningPrograms(
        reviewer=_stub_program(SimpleNamespace(review_markdown="# Review"))
    )
    output = programs.review(
        task="Fix bug",
        discovery_context="ctx",
        implementation_plan="plan",
        pi_completion_summary="done",
        command_output_summary="ok",
        git_diff="diff",
        vet_json="{}",
        workspace_artifacts="rules",
    )
    assert output.verdict == "FAIL"
    assert output.raw_verdict == ""
    assert "None" not in output.markdown


def _run_review(programs):
    return programs.review(
        task="Fix bug",
        discovery_context="ctx",
        implementation_plan="plan",
        pi_completion_summary="done",
        command_output_summary="ok",
        git_diff="diff",
        vet_json="{}",
        workspace_artifacts="rules",
    )


def test_review_forces_fail_when_p1_or_p2_findings_present():
    programs = DspyReasoningPrograms(
        reviewer=_stub_program(
            SimpleNamespace(verdict="PASS", review_markdown="# Review", p1_critical=["bug"])
        )
    )
    output = _run_review(programs)

    assert output.verdict == "FAIL"
    assert output.raw_verdict == "PASS"
    assert "bug" in output.markdown

    programs = DspyReasoningPrograms(
        reviewer=_stub_program(
            SimpleNamespace(verdict="PASS", review_markdown="# Review", p2_major=["dup logic"])
        )
    )
    output = _run_review(programs)

    assert output.verdict == "FAIL"
    assert "dup logic" in output.markdown


def test_review_keeps_pass_with_only_p3_findings():
    programs = DspyReasoningPrograms(
        reviewer=_stub_program(
            SimpleNamespace(verdict="PASS", review_markdown="# Review", p3_minor=["nit"])
        )
    )
    output = _run_review(programs)

    assert output.verdict == "PASS"
    assert "nit" in output.markdown


def test_review_markdown_carries_structured_findings_section():
    programs = DspyReasoningPrograms(
        reviewer=_stub_program(
            SimpleNamespace(
                verdict="FAIL",
                review_markdown="# Review",
                p1_critical=["broken auth"],
                p2_major=["duplicated logic"],
                p3_minor=["typo"],
            )
        )
    )
    output = _run_review(programs)

    assert "## Findings" in output.markdown
    assert "### P1 Critical\n- broken auth" in output.markdown
    assert "### P2 Major\n- duplicated logic" in output.markdown
    assert "### P3 Minor\n- typo" in output.markdown

    programs = DspyReasoningPrograms(
        reviewer=_stub_program(SimpleNamespace(verdict="PASS", review_markdown="# Review"))
    )
    output = _run_review(programs)

    assert "## Findings" not in output.markdown


def test_learn_tolerates_missing_attributes_with_empty_defaults():
    programs = DspyReasoningPrograms(learning_extractor=_stub_program(SimpleNamespace()))

    output = programs.learn(_evidence(), review_markdown="history")

    assert output.learnings == []
    assert output.examples == []
    assert '"learnings": []' in output.markdown

    programs = DspyReasoningPrograms(
        learning_extractor=_stub_program(
            SimpleNamespace(learnings=None, examples="not-a-list", rejected_observations=None)
        )
    )
    output = programs.learn(_evidence(), review_markdown="history")
    assert output.learnings == []
    assert output.examples == []


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
