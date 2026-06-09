from bd1.artifacts import ensure_workspace_dirs, write_json, write_text
from bd1.evidence import collect_evidence


def test_collect_evidence_reads_artifacts_tree_and_learnings(tmp_path, init_git_repo):
    repo = init_git_repo(tmp_path / "repo")
    ensure_workspace_dirs(repo)
    write_text(repo / ".artifacts" / "rules.md", "# Rules\n\nRead AGENTS.md first.\n")
    write_text(
        repo / ".artifacts" / "learning" / "lesson.md", "# Lesson\n\nPrefer focused tests.\n"
    )
    write_json(
        repo / ".learning" / "learnings" / "learning-1.json",
        {"rule": "Run route tests"},
        redact=False,
    )
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")

    evidence = collect_evidence(repo, task="Fix app")

    assert evidence.task == "Fix app"
    assert str(repo) == evidence.repo_path
    assert "src/app.py" in evidence.repo_tree
    assert "Read AGENTS.md first" in evidence.workspace_artifacts
    assert "Run route tests" in evidence.relevant_learnings
    assert "Prefer focused tests" in evidence.relevant_learnings


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
    write_json(
        repo / ".learning" / "learnings" / "learning-1.json",
        {"rule": "Nested repo learning"},
        redact=False,
    )

    evidence = collect_evidence(repo, task="Fix app")

    assert "Nested repo rule" in evidence.workspace_artifacts
    assert "Nested repo learning" in evidence.relevant_learnings
