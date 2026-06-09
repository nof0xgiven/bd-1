from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import dspy

from bd1.evidence import EvidencePackage


class DiscoverTaskContext(dspy.Signature):
    """Build a task-specific implementation context package."""

    task: str = dspy.InputField()
    workspace_artifacts: str = dspy.InputField()
    repo_evidence: str = dspy.InputField()
    relevant_learnings: str = dspy.InputField()
    external_examples: str = dspy.InputField()

    task_type: str = dspy.OutputField(desc="feature | bugfix | refactor | optimization | docs | chore")
    scope: list[str] = dspy.OutputField()
    source_of_truth: str = dspy.OutputField()
    files_to_read: list[dict[str, Any]] = dspy.OutputField()
    files_to_modify: list[dict[str, Any]] = dspy.OutputField()
    constraints: list[str] = dspy.OutputField()
    risks: list[str] = dspy.OutputField()
    context_package_markdown: str = dspy.OutputField()


class CreateImplementationPlan(dspy.Signature):
    """Create an implementation-ready technical plan from a context package."""

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
    """Decide whether the worktree is safe to merge."""

    task: str = dspy.InputField()
    implementation_plan: str = dspy.InputField()
    coder_summary: str = dspy.InputField()
    git_diff: str = dspy.InputField()
    test_output: str = dspy.InputField()
    vet_interpretation: str = dspy.InputField()
    workspace_artifacts: str = dspy.InputField()

    verdict: str = dspy.OutputField(desc="PASS | REVISE | FAIL")
    p1_critical: list[str] = dspy.OutputField()
    p2_major: list[str] = dspy.OutputField()
    p3_minor: list[str] = dspy.OutputField()
    revision_prompt: str = dspy.OutputField()
    review_markdown: str = dspy.OutputField()


class ExtractLearning(dspy.Signature):
    """Extract reusable engineering learnings from a completed run."""

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


@dataclass(frozen=True)
class ReviewOutput:
    verdict: str
    markdown: str

    def __post_init__(self) -> None:
        verdict = "PASS" if str(self.verdict).strip().upper() == "PASS" else "FAIL"
        object.__setattr__(self, "verdict", verdict)


@dataclass(frozen=True)
class LearningOutput:
    markdown: str


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
        return LearningOutput(markdown=markdown)


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


class DspyReasoningPrograms:
    def __init__(
        self,
        *,
        discovery: Any | None = None,
        planner: Any | None = None,
        reviewer: Any | None = None,
        learning_extractor: Any | None = None,
    ) -> None:
        self._discovery = discovery or DiscoveryProgram()
        self._planner = planner or PlanningProgram()
        self._reviewer = reviewer or ReviewProgram()
        self._learning_extractor = learning_extractor or LearningProgram()

    def discover(self, evidence: EvidencePackage) -> DiscoveryOutput:
        prediction = self._discovery(
            task=evidence.task,
            workspace_artifacts=evidence.workspace_artifacts,
            repo_evidence=evidence.repo_tree,
            relevant_learnings=evidence.relevant_learnings,
            external_examples=evidence.extra_context,
        )
        return DiscoveryOutput(markdown=str(prediction.context_package_markdown))

    def plan(self, evidence: EvidencePackage, *, discovery_context: str) -> PlanOutput:
        prediction = self._planner(
            task=evidence.task,
            context_package=discovery_context,
            workspace_rules=evidence.workspace_artifacts,
            relevant_learnings=evidence.relevant_learnings,
        )
        return PlanOutput(markdown=str(prediction.plan_markdown))

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
        return ReviewOutput(verdict=str(prediction.verdict), markdown=str(prediction.review_markdown))

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
        return LearningOutput(markdown=_format_learning_prediction(prediction))


def _format_coder_summary(discovery_context: str, pi_completion_summary: str) -> str:
    return "\n\n".join(
        [
            f"## Discovery Context\n{discovery_context}",
            f"## Pi Completion Summary\n{pi_completion_summary}",
        ]
    )


def _format_learning_prediction(prediction: Any) -> str:
    payload = {
        "learnings": getattr(prediction, "learnings", []),
        "examples": getattr(prediction, "examples", []),
        "rejected_observations": getattr(prediction, "rejected_observations", []),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


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
