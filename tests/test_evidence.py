from dataclasses import replace

from bd1.artifacts import ensure_workspace_dirs, write_text
from bd1.evidence import MAX_RELEVANT_LEARNINGS_BYTES, collect_evidence
from bd1.learning import LearningStore
from bd1.models import LearningRecord


def make_learning(learning_id: str, status: str, confidence: float, rule: str) -> LearningRecord:
    return LearningRecord(
        id=learning_id,
        created_at="2026-06-09T12:00:00Z",
        status=status,
        source_run_id="run-1",
        source_task="Fix bug",
        category="testing_pattern",
        applies_when="Changing API behavior",
        rule=rule,
        rationale="Because it caught a regression",
        evidence=[],
        tags=["testing"],
        confidence=confidence,
    )


def test_collect_evidence_reads_artifacts_tree_and_learnings(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    ensure_workspace_dirs(repo)
    write_text(repo / ".artifacts" / "rules.md", "# Rules\n\nRead AGENTS.md first.\n")
    write_text(
        repo / ".artifacts" / "learning" / "lesson.md", "# Lesson\n\nPrefer focused tests.\n"
    )
    store = LearningStore(tmp_path / "global" / "learning" / "demo")
    store.save_learning(make_learning("learning-1", "active", 0.9, "Run route tests"))
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")

    evidence = collect_evidence(repo, task="Fix app", learning_store=store)

    assert evidence.task == "Fix app"
    assert str(repo) == evidence.repo_path
    assert "src/app.py" in evidence.repo_tree
    assert "Read AGENTS.md first" in evidence.workspace_artifacts
    assert "Run route tests" in evidence.relevant_learnings
    assert "Prefer focused tests" in evidence.relevant_learnings


def test_collect_evidence_filters_rejected_and_superseded_learnings(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    ensure_workspace_dirs(repo)
    store = LearningStore(tmp_path / "global" / "learning" / "demo")
    store.save_learning(make_learning("learning-active", "active", 0.9, "Active rule"))
    store.save_learning(make_learning("learning-pending", "pending", 0.6, "Pending rule"))
    store.save_learning(make_learning("learning-rejected", "rejected", 0.1, "Rejected rule"))
    store.save_learning(make_learning("learning-superseded", "superseded", 0.95, "Superseded rule"))

    evidence = collect_evidence(repo, task="Fix app", learning_store=store)

    assert "Active rule" in evidence.relevant_learnings
    assert "Pending rule" in evidence.relevant_learnings
    assert "Rejected rule" not in evidence.relevant_learnings
    assert "Superseded rule" not in evidence.relevant_learnings


def test_collect_evidence_caps_learning_bytes_and_notes_truncation(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    ensure_workspace_dirs(repo)
    store = LearningStore(tmp_path / "global" / "learning" / "demo")
    big_rule = "x" * 20_000
    for index in range(8):
        learning = make_learning(f"learning-{index}", "active", 0.9, f"rule-{index} {big_rule}")
        store.save_learning(replace(learning, rationale=big_rule))

    evidence = collect_evidence(repo, task="Fix app", learning_store=store)

    assert len(evidence.relevant_learnings.encode("utf-8")) < MAX_RELEVANT_LEARNINGS_BYTES + 200
    assert "[truncated: relevant learnings exceeded" in evidence.relevant_learnings
    assert "section(s) omitted]" in evidence.relevant_learnings


def test_collect_evidence_without_store_reads_only_worktree_learning_markdown(
    tmp_path, init_git_repo
):
    repo = init_git_repo(tmp_path / "repo")
    ensure_workspace_dirs(repo)
    write_text(repo / ".artifacts" / "learning" / "lesson.md", "Worktree lesson.\n")

    evidence = collect_evidence(repo, task="Fix app")

    assert "Worktree lesson." in evidence.relevant_learnings


def test_collect_evidence_excludes_generated_and_dependency_directories(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    ensure_workspace_dirs(repo)
    included = repo / "src" / "feature.py"
    included.parent.mkdir()
    included.write_text("print('included')\n", encoding="utf-8")

    for relative in [
        ".git/ignored.py",
        ".sessions/session.md",
        ".venv/lib/site.py",
        "node_modules/pkg/index.js",
        "src/__pycache__/feature.pyc",
    ]:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ignored\n", encoding="utf-8")

    evidence = collect_evidence(repo, task="Fix app")

    assert "src/feature.py" in evidence.repo_tree
    assert ".git/ignored.py" not in evidence.repo_tree
    assert ".sessions/session.md" not in evidence.repo_tree
    assert ".venv/lib/site.py" not in evidence.repo_tree
    assert "node_modules/pkg/index.js" not in evidence.repo_tree
    assert "src/__pycache__/feature.pyc" not in evidence.repo_tree


def test_collect_evidence_includes_explicit_extra_context(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    ensure_workspace_dirs(repo)

    evidence = collect_evidence(repo, task="Fix app", extra_context="Use the narrowest diff.")

    assert evidence.extra_context == "Use the narrowest diff."


def test_collect_evidence_omits_task_history_from_workspace_artifacts(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    ensure_workspace_dirs(repo)
    write_text(repo / ".artifacts" / "rules.md", "# Rules\n\nDurable rule.\n")
    write_text(
        repo / ".artifacts" / "context" / "architecture.md", "# Architecture\n\nDurable context.\n"
    )
    write_text(repo / ".artifacts" / "plans" / "old-task.md", "# Old Plan\n\nTask-specific plan.\n")
    write_text(repo / ".artifacts" / "completed" / "run.md", "# Completed\n\nTask history.\n")

    evidence = collect_evidence(repo, task="Fix app")

    assert "Durable rule" in evidence.workspace_artifacts
    assert "Durable context" in evidence.workspace_artifacts
    assert "Task-specific plan" not in evidence.workspace_artifacts
    assert "Task history" not in evidence.workspace_artifacts


def test_collect_evidence_does_not_exclude_repo_nested_under_excluded_parent_name(
    tmp_path, init_git_repo
):
    repo = init_git_repo(tmp_path / "node_modules" / "repo")
    ensure_workspace_dirs(repo)
    write_text(repo / ".artifacts" / "rules.md", "# Rules\n\nNested repo rule.\n")
    store = LearningStore(tmp_path / "global" / "learning" / "demo")
    store.save_learning(make_learning("learning-1", "active", 0.9, "Nested repo learning"))

    evidence = collect_evidence(repo, task="Fix app", learning_store=store)

    assert "Nested repo rule" in evidence.workspace_artifacts
    assert "Nested repo learning" in evidence.relevant_learnings
