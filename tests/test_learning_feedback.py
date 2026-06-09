import json

from bd1.feedback import write_feedback
from bd1.learning import ExampleStore, LearningStore
from bd1.models import FeedbackRecord, LearningRecord


def make_learning(learning_id: str, status: str, confidence: float) -> LearningRecord:
    return LearningRecord(
        id=learning_id,
        created_at="2026-06-09T12:00:00Z",
        status=status,
        source_run_id="run-1",
        source_task="Fix bug",
        category="testing_pattern",
        applies_when="Changing API behavior",
        rule=f"Rule for {learning_id}",
        rationale="Evidence included TOKEN=secret-token",
        evidence=[{"artifact": ".artifacts/reviews/run-1.md", "excerpt": "Review finding"}],
        tags=["testing"],
        confidence=confidence,
    )


def test_write_feedback_captures_fields_and_redacts(tmp_path):
    feedback = FeedbackRecord(
        run_id="run-1",
        created_at="2026-06-09T12:00:00Z",
        outcome="wrong_behavior",
        wrong_or_missing="Plan missed route coverage and OPENAI_API_KEY=sk-secret",
        expected="Plan includes integration test",
        affected_artifact=".artifacts/plans/fix.md",
        commit="abc123",
        learning_candidate=True,
    )

    path = write_feedback(tmp_path, feedback)

    assert path == tmp_path / ".sessions" / "run-1" / "feedback.json"
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["run_id"] == "run-1"
    assert data["outcome"] == "wrong_behavior"
    assert data["expected"] == "Plan includes integration test"
    assert data["affected_artifact"] == ".artifacts/plans/fix.md"
    assert data["commit"] == "abc123"
    assert data["learning_candidate"] is True
    assert "sk-secret" not in text
    assert "[REDACTED]" in data["wrong_or_missing"]


def test_learning_store_saves_learning_with_confidence_status(tmp_path):
    store = LearningStore(tmp_path)

    path = store.save_learning(make_learning("learning-1", "pending", 0.91))

    assert path == tmp_path / ".learning" / "learnings" / "learning-1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == "learning-1"
    assert data["status"] == "active"
    assert data["confidence"] == 0.91
    assert "secret-token" not in path.read_text(encoding="utf-8")


def test_learning_store_rebuilds_index_with_all_statuses(tmp_path):
    store = LearningStore(tmp_path)
    store.save_learning(make_learning("learning-active", "pending", 0.9))
    store.save_learning(make_learning("learning-pending", "active", 0.6))
    store.save_learning(make_learning("learning-rejected", "active", 0.2))
    store.save_learning(make_learning("learning-superseded", "superseded", 0.95))

    path = store.rebuild_index()

    assert path == tmp_path / ".learning" / "index.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    assert index["active"] == ["learning-active"]
    assert index["pending"] == ["learning-pending"]
    assert index["rejected"] == ["learning-rejected"]
    assert index["superseded"] == ["learning-superseded"]


def test_example_store_appends_examples(tmp_path):
    store = ExampleStore(tmp_path)

    first_path = store.append_example("review", {"verdict": "FAIL"})
    second_path = store.append_example("review", {"verdict": "PASS"})

    assert first_path == tmp_path / ".examples" / "review.jsonl"
    assert second_path == first_path
    lines = first_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"verdict": "FAIL"}
    assert json.loads(lines[1]) == {"verdict": "PASS"}


def test_example_store_redacts_payloads_without_breaking_json(tmp_path):
    store = ExampleStore(tmp_path)

    path = store.append_example("review", {"token": 123, "passed": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "passed": True,
        "token": "[REDACTED]",
    }


def test_terminal_learning_summary_writes_learning_and_example_counts(tmp_path):
    learning_store = LearningStore(tmp_path)
    learning_store.save_learning(make_learning("learning-active", "active", 0.88))
    learning_store.save_learning(make_learning("learning-pending", "active", 0.7))
    learning_store.save_learning(make_learning("learning-rejected", "active", 0.1))
    examples = ExampleStore(tmp_path)
    examples.append_example("review", {"verdict": "PASS"})
    examples.append_example("learning", {"kind": "terminal"})

    path = learning_store.write_terminal_summary(examples)

    assert path == tmp_path / ".artifacts" / "learning" / "terminal-summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert summary["active"] == 1
    assert summary["pending"] == 1
    assert summary["rejected"] == 1
    assert summary["examples"] == {"learning": 1, "review": 1, "total": 2}
