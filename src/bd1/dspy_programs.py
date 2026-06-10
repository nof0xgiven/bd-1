from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import dspy

from bd1.errors import ReasoningOutputError
from bd1.evidence import EvidencePackage
from bd1.repo_tools import RepoTools


class DiscoverTaskContext(dspy.Signature):
    """Build a task-specific implementation context package for a coding agent.

    You are a discovery agent. Your output is the coding agent's entire world:
    it must enable a correct implementation on the first attempt. Do not assume —
    if you cannot prove a claim from the repository evidence, label it explicitly
    as an ambiguity in the context package. Find a source of truth for the change:
    either an existing reference implementation in this repository or a proven
    external example, and cite it. Prefer minimal-but-sufficient inclusion:
    everything the coding agent needs, nothing irrelevant. For every file excerpt
    include the file path; for files to read, explain why each matters. Surface
    concrete gotchas tied to this repository, constraints discovered from the
    workspace artifacts, and how the coding agent can validate its work.
    """

    task: str = dspy.InputField()
    workspace_artifacts: str = dspy.InputField()
    repo_evidence: str = dspy.InputField()
    relevant_learnings: str = dspy.InputField()
    external_examples: str = dspy.InputField()

    task_type: str = dspy.OutputField(
        desc="feature | bugfix | refactor | optimization | docs | chore"
    )
    scope: list[str] = dspy.OutputField()
    source_of_truth: str = dspy.OutputField()
    files_to_read: list[dict[str, Any]] = dspy.OutputField()
    files_to_modify: list[dict[str, Any]] = dspy.OutputField()
    constraints: list[str] = dspy.OutputField()
    risks: list[str] = dspy.OutputField()
    context_package_markdown: str = dspy.OutputField()


class CreateImplementationPlan(dspy.Signature):
    """Create an implementation-ready technical plan from a context package.

    You are a senior software architect. Assume the implementing engineer is
    skilled but has zero context for this codebase and questionable taste:
    document which files to touch for each step, what to check, and how to test.
    Start from a current-state analysis: existing responsibilities, data flow,
    and code that should be reused or extended — never duplicate what exists.
    Prefer the smallest change that cleanly solves the problem (DRY, YAGNI, TDD,
    frequent commits). Specify file-by-file impact with ordering constraints,
    state/data-flow changes, error handling for each operation that can fail,
    and edge cases (empty collections, missing values, interrupted operations).
    Do not add layers or abstractions without a concrete benefit. Make every
    assumption explicit and flag unknowns to validate during implementation.
    """

    task: str = dspy.InputField()
    context_package: str = dspy.InputField()
    workspace_rules: str = dspy.InputField()
    relevant_learnings: str = dspy.InputField()

    summary: str = dspy.OutputField()
    current_state_analysis: str = dspy.OutputField()
    design: str = dspy.OutputField()
    file_by_file_impact: list[dict[str, Any]] = dspy.OutputField()
    implementation_order: list[str] = dspy.OutputField()
    acceptance_criteria: list[str] = dspy.OutputField()
    plan_markdown: str = dspy.OutputField()


class DecideReviewOutcome(dspy.Signature):
    """Decide whether the worktree is safe to merge into production right now.

    You are a senior code reviewer enforcing production readiness. The decision
    is binary: PASS means approved for production merge right now; anything that
    clearly needs refactoring, cleanup, or more work is FAIL. Review for fit, not
    just function: the change must match this project's architecture, patterns,
    and conventions as documented in the workspace artifacts. The code must
    satisfy the original task, be simple and readable, avoid duplicated logic,
    contain no TODO/FIXME markers or leftover debug logs, handle errors at
    external boundaries, and maintain meaningful test coverage. Testing doctrine:
    no mock-only tests — a test that would pass even when the feature is broken
    counts against the change. Quality warnings are acceptable; errors are not.
    When in doubt about production readiness, treat the issue as critical and
    do not approve. List findings as P1 (critical), P2 (major), P3 (minor):
    P1 or P2 findings force FAIL; a PASS may carry only P3 findings.
    """

    task: str = dspy.InputField()
    implementation_plan: str = dspy.InputField()
    coder_summary: str = dspy.InputField()
    git_diff: str = dspy.InputField()
    test_output: str = dspy.InputField()
    vet_interpretation: str = dspy.InputField()
    workspace_artifacts: str = dspy.InputField()

    verdict: str = dspy.OutputField(desc="PASS | FAIL")
    p1_critical: list[str] = dspy.OutputField()
    p2_major: list[str] = dspy.OutputField()
    p3_minor: list[str] = dspy.OutputField()
    review_markdown: str = dspy.OutputField()


class ExtractLearning(dspy.Signature):
    """Extract reusable engineering learnings from a completed run.

    Compound engineering: each unit of work should make subsequent units easier.
    Analyze the run record, diff, review history, and PR feedback for mistakes
    that were corrected, wins worth repeating, and workspace-specific constraints
    that were discovered the hard way. Each learning must be a durable, reusable
    rule for FUTURE tasks in this workspace — not a restatement of what this task
    did. Reject observations that are task-specific trivia, already obvious from
    the workspace artifacts, or speculative. Each learning needs: a rule, when it
    applies, when to avoid it, the rationale, evidence from this run, and a
    calibrated confidence (0.0-1.0) — overclaiming confidence pollutes the store.
    """

    run_record: str = dspy.InputField()
    final_diff: str = dspy.InputField()
    pr_feedback: str = dspy.InputField()
    review_history: str = dspy.InputField()

    learnings: list[dict[str, Any]] = dspy.OutputField()
    examples: list[dict[str, Any]] = dspy.OutputField()
    rejected_observations: list[str] = dspy.OutputField()


@dataclass(frozen=True)
class DiscoveryOutput:
    markdown: str


@dataclass(frozen=True)
class PlanOutput:
    markdown: str


def normalize_review_verdict(raw: str) -> str:
    """Binary verdict: token-match PASS or FAIL; anything unparseable fails closed."""
    for token in re.findall(r"[A-Za-z]+", str(raw)):
        upper = token.upper()
        if upper in ("PASS", "FAIL"):
            return upper
    return "FAIL"


@dataclass(frozen=True)
class ReviewOutput:
    verdict: str
    markdown: str
    raw_verdict: str = ""

    def __post_init__(self) -> None:
        raw = str(self.verdict)
        if not self.raw_verdict:
            object.__setattr__(self, "raw_verdict", raw)
        object.__setattr__(self, "verdict", normalize_review_verdict(raw))


@dataclass(frozen=True)
class LearningOutput:
    markdown: str
    learnings: list[dict[str, Any]] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)


class ReasoningPrograms(Protocol):
    def discover(self, evidence: EvidencePackage) -> DiscoveryOutput: ...

    def plan(self, evidence: EvidencePackage, *, discovery_context: str) -> PlanOutput: ...

    def review(
        self,
        *,
        task: str,
        discovery_context: str,
        implementation_plan: str,
        pi_completion_summary: str,
        command_output_summary: str,
        git_diff: str,
        vet_json: str,
        workspace_artifacts: str,
    ) -> ReviewOutput: ...

    def learn(
        self,
        evidence: EvidencePackage,
        *,
        review_markdown: str,
        final_diff: str = "",
        pr_feedback: str = "",
    ) -> LearningOutput: ...


class TemplateReasoningPrograms:
    """Deterministic fallback for tests only."""

    def discover(self, evidence: EvidencePackage) -> DiscoveryOutput:
        return DiscoveryOutput(markdown=_format_context_package(evidence))

    def plan(self, evidence: EvidencePackage, *, discovery_context: str) -> PlanOutput:
        markdown = "\n\n".join(
            [
                "# Implementation Plan",
                f"## Task\n{evidence.task}",
                f"## Discovery Context\n{discovery_context}",
                f"## Repo Tree\n{evidence.repo_tree}",
            ]
        )
        return PlanOutput(markdown=markdown)

    def review(
        self,
        *,
        task: str,
        discovery_context: str,
        implementation_plan: str,
        pi_completion_summary: str,
        command_output_summary: str,
        git_diff: str,
        vet_json: str,
        workspace_artifacts: str,
    ) -> ReviewOutput:
        markdown = "\n\n".join(
            [
                "# Review",
                f"## Task\n{task}",
                f"## Discovery Context\n{discovery_context}",
                f"## Implementation Plan\n{implementation_plan}",
                f"## Pi Completion Summary\n{pi_completion_summary}",
                f"## Command Output Summary\n{command_output_summary}",
                f"## Git Diff\n{git_diff}",
                f"## Vet JSON\n{vet_json}",
                f"## Workspace Artifacts\n{workspace_artifacts}",
            ]
        )
        return ReviewOutput(verdict="PASS", markdown=markdown)

    def learn(
        self,
        evidence: EvidencePackage,
        *,
        review_markdown: str,
        final_diff: str = "",
        pr_feedback: str = "",
    ) -> LearningOutput:
        markdown = "\n\n".join(
            [
                "# Learning Candidates",
                f"## Task\n{evidence.task}",
                f"## Final Diff\n{final_diff}",
                f"## PR Feedback\n{pr_feedback}",
                f"## Review\n{review_markdown}",
            ]
        )
        return LearningOutput(
            markdown=markdown,
            learnings=[
                {
                    "rule": f"Template learning for task: {evidence.task}",
                    "category": "process",
                    "applies_when": "Running similar tasks in this workspace.",
                    "rationale": review_markdown,
                    "confidence": 0.5,
                    "tags": ["template"],
                }
            ],
        )


class DiscoveryProgram(dspy.Module):
    def __init__(self) -> None:
        self.discover = dspy.ChainOfThought(DiscoverTaskContext)

    def forward(
        self,
        *,
        task: str,
        workspace_artifacts: str,
        repo_evidence: str,
        relevant_learnings: str,
        external_examples: str,
    ):
        return self.discover(
            task=task,
            workspace_artifacts=workspace_artifacts,
            repo_evidence=repo_evidence,
            relevant_learnings=relevant_learnings,
            external_examples=external_examples,
        )


class PlanningProgram(dspy.Module):
    def __init__(self) -> None:
        self.plan = dspy.ChainOfThought(CreateImplementationPlan)

    def forward(
        self,
        *,
        task: str,
        context_package: str,
        workspace_rules: str,
        relevant_learnings: str,
    ):
        return self.plan(
            task=task,
            context_package=context_package,
            workspace_rules=workspace_rules,
            relevant_learnings=relevant_learnings,
        )


class ReviewProgram(dspy.Module):
    def __init__(self) -> None:
        self.review = dspy.ChainOfThought(DecideReviewOutcome)

    def forward(
        self,
        *,
        task: str,
        implementation_plan: str,
        coder_summary: str,
        git_diff: str,
        test_output: str,
        vet_interpretation: str,
        workspace_artifacts: str,
    ):
        return self.review(
            task=task,
            implementation_plan=implementation_plan,
            coder_summary=coder_summary,
            git_diff=git_diff,
            test_output=test_output,
            vet_interpretation=vet_interpretation,
            workspace_artifacts=workspace_artifacts,
        )


class LearningProgram(dspy.Module):
    def __init__(self) -> None:
        self.extract = dspy.Predict(ExtractLearning)

    def forward(
        self,
        *,
        run_record: str,
        final_diff: str,
        pr_feedback: str,
        review_history: str,
    ):
        return self.extract(
            run_record=run_record,
            final_diff=final_diff,
            pr_feedback=pr_feedback,
            review_history=review_history,
        )


def build_discovery_react(repo_root: str, max_iters: int):
    """Default factory: a dspy.ReAct over DiscoverTaskContext with repo tools."""
    tools = RepoTools(repo_root)
    return dspy.ReAct(
        DiscoverTaskContext,
        tools=[tools.list_tree, tools.read_file, tools.search_text],
        max_iters=max_iters,
    )


class DspyReasoningPrograms:
    def __init__(
        self,
        *,
        discovery: Any | None = None,
        planner: Any | None = None,
        reviewer: Any | None = None,
        learning_extractor: Any | None = None,
        discovery_max_iters: int = 12,
        discovery_react_factory: Any | None = None,
    ) -> None:
        self._discovery_max_iters = discovery_max_iters
        self._discovery = discovery or DiscoveryProgram()
        self._planner = planner or PlanningProgram()
        self._reviewer = reviewer or ReviewProgram()
        self._learning_extractor = learning_extractor or LearningProgram()
        self._discovery_react_factory = discovery_react_factory or build_discovery_react

    def discover(self, evidence: EvidencePackage) -> DiscoveryOutput:
        inputs = dict(
            task=evidence.task,
            workspace_artifacts=evidence.workspace_artifacts,
            repo_evidence=evidence.repo_tree,
            relevant_learnings=evidence.relevant_learnings,
            external_examples=evidence.extra_context,
        )
        try:
            react = self._discovery_react_factory(evidence.repo_path, self._discovery_max_iters)
            prediction = react(**inputs)
            markdown = _required_markdown(prediction, "context_package_markdown", "Discovery")
            return DiscoveryOutput(markdown=markdown)
        except Exception:
            # ReAct failures (iteration exhaustion, tool/adapter errors) must
            # degrade to single-shot discovery, never block the run on their
            # own. A failure of the fallback itself still raises
            # ReasoningOutputError via _required_markdown.
            prediction = self._discovery(**inputs)
            markdown = _required_markdown(prediction, "context_package_markdown", "Discovery")
            note = "\n\n> Note: tool-using discovery failed; single-shot fallback was used.\n"
            return DiscoveryOutput(markdown=markdown + note)

    def plan(self, evidence: EvidencePackage, *, discovery_context: str) -> PlanOutput:
        prediction = self._planner(
            task=evidence.task,
            context_package=discovery_context,
            workspace_rules=evidence.workspace_artifacts,
            relevant_learnings=evidence.relevant_learnings,
        )
        return PlanOutput(markdown=_required_markdown(prediction, "plan_markdown", "Planning"))

    def review(
        self,
        *,
        task: str,
        discovery_context: str,
        implementation_plan: str,
        pi_completion_summary: str,
        command_output_summary: str,
        git_diff: str,
        vet_json: str,
        workspace_artifacts: str,
    ) -> ReviewOutput:
        prediction = self._reviewer(
            task=task,
            implementation_plan=implementation_plan,
            coder_summary=_format_coder_summary(discovery_context, pi_completion_summary),
            git_diff=git_diff,
            test_output=command_output_summary,
            vet_interpretation=vet_json,
            workspace_artifacts=workspace_artifacts,
        )
        p1 = _list_or_default(prediction, "p1_critical")
        p2 = _list_or_default(prediction, "p2_major")
        p3 = _list_or_default(prediction, "p3_minor")
        raw_verdict = _text_or_default(prediction, "verdict")
        verdict = "FAIL" if p1 or p2 else raw_verdict
        markdown = _required_markdown(prediction, "review_markdown", "Review")
        return ReviewOutput(
            verdict=verdict,
            markdown=markdown + _format_findings_section(p1, p2, p3),
            raw_verdict=raw_verdict,
        )

    def learn(
        self,
        evidence: EvidencePackage,
        *,
        review_markdown: str,
        final_diff: str = "",
        pr_feedback: str = "",
    ) -> LearningOutput:
        prediction = self._learning_extractor(
            run_record=_format_context_package(evidence),
            final_diff=final_diff,
            pr_feedback=pr_feedback,
            review_history=review_markdown,
        )
        return LearningOutput(
            markdown=_format_learning_prediction(prediction),
            learnings=_list_or_default(prediction, "learnings"),
            examples=_list_or_default(prediction, "examples"),
        )


def _format_coder_summary(discovery_context: str, pi_completion_summary: str) -> str:
    return "\n\n".join(
        [
            f"## Discovery Context\n{discovery_context}",
            f"## Pi Completion Summary\n{pi_completion_summary}",
        ]
    )


def _text_or_default(prediction: Any, name: str) -> str:
    """Safe text extraction: missing or None attributes become "" not "None"."""
    value = getattr(prediction, name, "")
    return "" if value is None else str(value)


def _required_markdown(prediction: Any, name: str, program: str) -> str:
    text = _text_or_default(prediction, name)
    if not text.strip():
        raise ReasoningOutputError(f"{program} program returned empty {name}.")
    return text


def _list_or_default(prediction: Any, name: str) -> list[Any]:
    value = getattr(prediction, name, None)
    return value if isinstance(value, list) else []


def _format_findings_section(p1: list[Any], p2: list[Any], p3: list[Any]) -> str:
    sections = [
        f"### {title}\n" + "\n".join(f"- {item}" for item in items)
        for title, items in (("P1 Critical", p1), ("P2 Major", p2), ("P3 Minor", p3))
        if items
    ]
    if not sections:
        return ""
    return "\n\n## Findings\n" + "\n".join(sections)


def _format_learning_prediction(prediction: Any) -> str:
    payload = {
        "learnings": _list_or_default(prediction, "learnings"),
        "examples": _list_or_default(prediction, "examples"),
        "rejected_observations": _list_or_default(prediction, "rejected_observations"),
    }
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


def _format_context_package(evidence: EvidencePackage) -> str:
    return "\n\n".join(
        [
            "# Context Package",
            f"## Task\n{evidence.task}",
            f"## Repository\n{evidence.repo_path}",
            f"## Repo Tree\n{evidence.repo_tree}",
            f"## Workspace Artifacts\n{evidence.workspace_artifacts}",
            f"## Relevant Learnings\n{evidence.relevant_learnings}",
            f"## Extra Context\n{evidence.extra_context}",
        ]
    )
