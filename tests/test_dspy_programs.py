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
    build_discovery_react,
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


def test_discovery_context_package_field_carries_output_template():
    desc = DiscoverTaskContext.output_fields["context_package_markdown"].json_schema_extra["desc"]
    for heading in [
        "# Context Package:",
        "## Task Understanding",
        "## Source of Truth",
        "## Architecture Overview",
        "## Files to Read",
        "## Files to Create or Modify",
        "## Patterns to Follow",
        "## Constraints and Requirements",
        "## Potential Gotchas",
        "## How to Validate",
        "## Implementation Hints",
    ]:
        assert heading in desc
    # Ambiguities live in Potential Gotchas — same rule as the docstring.
    assert "ambiguities" in desc


def test_source_of_truth_is_scoped_to_provable_evidence():
    # Discovery has repo tools, the external_examples input, and (when
    # configured) external research tools via MCP: a missing source of truth
    # must be recorded, never invented as a citation. Docstring and field
    # desc state the same rule, including the conditional tool leg.
    doc = DiscoverTaskContext.__doc__
    desc = DiscoverTaskContext.output_fields["context_package_markdown"].json_schema_extra["desc"]
    for text in (doc, desc):
        assert "external_examples" in text
        assert "external research tools" in text
        assert "never invent a citation" in text


def test_plan_markdown_field_carries_output_template():
    desc = CreateImplementationPlan.output_fields["plan_markdown"].json_schema_extra["desc"]
    for heading in [
        "# Implementation Plan:",
        "## Summary",
        "## Acceptance Criteria",
        "## Current-State Analysis",
        "## Design",
        "## File-by-File Impact",
        "## Trade-offs and Alternatives",
        "## Risks",
        "## Implementation Order",
    ]:
        assert heading in desc


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


class _ExplodingReact:
    def __call__(self, **kwargs):
        raise RuntimeError("react exhausted")


class _RecordingFallback:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(context_package_markdown="# Context Package: fallback")


def _react_evidence(tmp_path, **overrides) -> EvidencePackage:
    fields = dict(
        task="t",
        repo_path=str(tmp_path),
        repo_tree="tree",
        workspace_artifacts="wa",
        relevant_learnings="rl",
        extra_context="",
    )
    fields.update(overrides)
    return EvidencePackage(**fields)


def test_discover_uses_react_then_falls_back_to_single_shot(tmp_path, capsys):
    fallback = _RecordingFallback()
    programs = DspyReasoningPrograms(
        discovery=fallback, discovery_react_factory=lambda root, max_iters: _ExplodingReact()
    )

    output = programs.discover(_react_evidence(tmp_path))

    assert "fallback" in output.markdown
    assert "single-shot fallback" in output.markdown.lower()
    # The note must surface the failure cause so operators can distinguish
    # transient exhaustion from "ReAct never works in this workspace".
    assert "RuntimeError" in output.markdown
    assert "react exhausted" in output.markdown
    assert len(fallback.calls) == 1
    stderr = capsys.readouterr().err
    assert "tool-using discovery failed" in stderr
    assert "RuntimeError" in stderr
    assert "react exhausted" in stderr


def test_discover_prefers_react_result(tmp_path, capsys):
    def react(**kwargs):
        return SimpleNamespace(context_package_markdown="# Context Package: via react")

    fallback = _RecordingFallback()
    programs = DspyReasoningPrograms(
        discovery=fallback,
        discovery_react_factory=lambda root, max_iters: react,
    )

    output = programs.discover(_react_evidence(tmp_path))

    assert "via react" in output.markdown
    assert "fallback" not in output.markdown.lower()
    assert fallback.calls == []
    assert capsys.readouterr().err == ""


def test_discover_passes_artifacts_and_learnings_to_react(tmp_path):
    seen = {}

    def react(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(context_package_markdown="# Context Package: ok")

    programs = DspyReasoningPrograms(
        discovery=_RecordingFallback(),
        discovery_react_factory=lambda root, max_iters: react,
    )

    programs.discover(
        _react_evidence(
            tmp_path,
            workspace_artifacts="THE-ARTIFACTS",
            relevant_learnings="THE-LEARNINGS",
        )
    )

    assert seen["workspace_artifacts"] == "THE-ARTIFACTS"
    assert seen["relevant_learnings"] == "THE-LEARNINGS"


def test_discover_react_factory_receives_repo_path_and_max_iters(tmp_path):
    seen = {}

    def factory(root, max_iters):
        seen["root"] = root
        seen["max_iters"] = max_iters

        def react(**kwargs):
            return SimpleNamespace(context_package_markdown="# Context Package: ok")

        return react

    programs = DspyReasoningPrograms(
        discovery=_RecordingFallback(),
        discovery_react_factory=factory,
        discovery_max_iters=9,
    )

    programs.discover(_react_evidence(tmp_path))

    assert seen["root"] == str(tmp_path)
    assert seen["max_iters"] == 9


def _fixture_server_command() -> str:
    import shlex
    import sys as _sys
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "echo_mcp_server.py"
    return f"{shlex.quote(_sys.executable)} {shlex.quote(str(fixture))}"


def test_discover_with_mcp_servers_builds_react_over_repo_and_mcp_tools(tmp_path):
    seen = {}

    def factory(root, max_iters, extra_tools=()):
        real = build_discovery_react(root, max_iters, extra_tools=extra_tools)
        seen["tool_names"] = set(real.tools.keys())
        seen["max_iters"] = max_iters

        class AsyncReact:
            async def acall(self, **kwargs):
                seen["inputs"] = kwargs
                return SimpleNamespace(context_package_markdown="# Context Package: via mcp react")

        return AsyncReact()

    fallback = _RecordingFallback()
    programs = DspyReasoningPrograms(
        discovery=fallback,
        discovery_react_factory=factory,
        discovery_max_iters=5,
        discovery_mcp_servers=[_fixture_server_command()],
    )

    output = programs.discover(_react_evidence(tmp_path, workspace_artifacts="THE-ARTIFACTS"))

    assert "via mcp react" in output.markdown
    assert fallback.calls == []
    assert {"list_tree", "read_file", "search_text", "echo"}.issubset(seen["tool_names"])
    assert seen["max_iters"] == 5
    assert seen["inputs"]["workspace_artifacts"] == "THE-ARTIFACTS"


def test_discover_with_all_mcp_servers_failing_still_runs_repo_only_react(tmp_path, capsys):
    # MCP failure must not force the single-shot fallback: the ReAct still
    # runs with repo tools only.
    seen = {}

    def factory(root, max_iters, extra_tools=()):
        seen["extra_tools"] = list(extra_tools)

        def react(**kwargs):
            return SimpleNamespace(context_package_markdown="# Context Package: repo only")

        return react

    fallback = _RecordingFallback()
    programs = DspyReasoningPrograms(
        discovery=fallback,
        discovery_react_factory=factory,
        discovery_mcp_servers=["definitely-not-a-real-binary-xyz"],
    )

    output = programs.discover(_react_evidence(tmp_path))

    assert "repo only" in output.markdown
    assert fallback.calls == []
    assert seen["extra_tools"] == []
    stderr = capsys.readouterr().err
    assert "bd-1: mcp server failed, continuing without it" in stderr
    assert "single-shot fallback" not in stderr


def test_discover_with_mcp_servers_inside_running_loop_falls_back_without_warning(
    tmp_path, capsys, recwarn
):
    # Embedding scenarios: discover() called from inside a running event loop
    # cannot use asyncio.run. It must fall back to single-shot discovery
    # without leaking an unawaited _discover_async coroutine (RuntimeWarning).
    import asyncio
    import gc

    fallback = _RecordingFallback()
    programs = DspyReasoningPrograms(
        discovery=fallback,
        discovery_react_factory=lambda root, max_iters, extra_tools=(): _ExplodingReact(),
        discovery_mcp_servers=["definitely-not-a-real-binary-xyz"],
    )

    async def call_from_running_loop():
        return programs.discover(_react_evidence(tmp_path))

    output = asyncio.run(call_from_running_loop())
    gc.collect()  # force collection so any unawaited coroutine warns now

    assert "single-shot fallback" in output.markdown.lower()
    assert len(fallback.calls) == 1
    assert "tool-using discovery failed" in capsys.readouterr().err
    runtime_warnings = [w for w in recwarn.list if issubclass(w.category, RuntimeWarning)]
    assert runtime_warnings == []


def test_discover_with_mcp_servers_falls_back_when_react_itself_fails(tmp_path, capsys):
    fallback = _RecordingFallback()
    programs = DspyReasoningPrograms(
        discovery=fallback,
        discovery_react_factory=lambda root, max_iters, extra_tools=(): _ExplodingReact(),
        discovery_mcp_servers=["definitely-not-a-real-binary-xyz"],
    )

    output = programs.discover(_react_evidence(tmp_path))

    assert "fallback" in output.markdown
    assert "react exhausted" in output.markdown
    assert len(fallback.calls) == 1
    assert "tool-using discovery failed" in capsys.readouterr().err


def test_build_discovery_react_registers_extra_tools_after_repo_tools(tmp_path):
    import dspy

    def fetch_docs(query: str) -> str:
        """Fetch documentation for a query."""
        return query

    react = build_discovery_react(str(tmp_path), 7, extra_tools=[dspy.Tool(fetch_docs)])

    assert {"list_tree", "read_file", "search_text", "fetch_docs"}.issubset(react.tools.keys())


def test_build_discovery_react_registers_repo_tools_and_max_iters(tmp_path):
    react = build_discovery_react(str(tmp_path), 7)

    assert react.max_iters == 7
    assert {"list_tree", "read_file", "search_text"}.issubset(react.tools.keys())
    for name in ("list_tree", "read_file", "search_text"):
        assert react.tools[name].desc  # docstrings survive as tool descriptions


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


def test_template_profile_returns_all_six_artifacts():
    programs = TemplateReasoningPrograms()
    output = programs.profile(repo_evidence="tree", product_description="a product")
    assert set(output.artifacts) == {
        "architecture",
        "system_patterns",
        "testing",
        "design",
        "rules",
        "product",
    }
    assert "a product" in output.artifacts["product"]


def test_dspy_profile_maps_prediction_fields():
    prediction = SimpleNamespace(
        architecture_markdown="arch",
        system_patterns_markdown="pat",
        testing_markdown="test",
        design_markdown="des",
        rules_markdown="rules",
        product_markdown="prod",
    )
    programs = DspyReasoningPrograms(
        profiler=_stub_program(prediction),
        discovery_react_factory=lambda root, max_iters: _stub_program(None),
    )
    output = programs.profile(repo_evidence="tree", product_description="p")
    assert output.artifacts["architecture"] == "arch"
    assert output.artifacts["rules"] == "rules"


def test_dspy_profile_raises_on_empty_required_field():
    prediction = SimpleNamespace(
        architecture_markdown="",
        system_patterns_markdown="pat",
        testing_markdown="t",
        design_markdown="d",
        rules_markdown="r",
        product_markdown="p",
    )
    programs = DspyReasoningPrograms(profiler=_stub_program(prediction))
    with pytest.raises(ReasoningOutputError):
        programs.profile(repo_evidence="tree", product_description="p")


def test_profile_fields_match_workspace_artifact_keys():
    from bd1.dspy_programs import _PROFILE_FIELDS
    from bd1.workspace import PROFILE_ARTIFACTS

    assert set(_PROFILE_FIELDS) == set(PROFILE_ARTIFACTS)
