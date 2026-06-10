import json

from bd1.dspy_programs import LearningOutput
from bd1.feedback import write_feedback, write_feedback_in_dir
from bd1.learning import (
    ExampleStore,
    LearningStore,
    learning_records_from_output,
    learning_root,
)
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


def make_feedback(run_id: str = "run-1") -> FeedbackRecord:
    return FeedbackRecord(
        run_id=run_id,
        created_at="2026-06-09T12:00:00Z",
        outcome="wrong_behavior",
        wrong_or_missing="Plan missed route coverage and OPENAI_API_KEY=sk-secret",
        expected="Plan includes integration test",
        affected_artifact=".artifacts/plans/fix.md",
        commit="abc123",
        learning_candidate=True,
    )


def test_write_feedback_captures_fields_and_redacts(tmp_path):
    path = write_feedback(tmp_path, make_feedback())

    assert path == tmp_path / ".sessions" / "run-1" / "feedback-001.json"
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


def test_write_feedback_sequences_files_instead_of_overwriting(tmp_path):
    first = write_feedback(tmp_path, make_feedback())
    second = write_feedback(tmp_path, make_feedback())
    third = write_feedback(tmp_path, make_feedback())

    assert first.name == "feedback-001.json"
    assert second.name == "feedback-002.json"
    assert third.name == "feedback-003.json"
    assert first.exists() and second.exists() and third.exists()
    assert json.loads(first.read_text(encoding="utf-8"))["run_id"] == "run-1"


def test_write_feedback_in_dir_supports_archive_fallback(tmp_path):
    archive_dir = tmp_path / "runs" / "run-1"

    first = write_feedback_in_dir(archive_dir, make_feedback())
    second = write_feedback_in_dir(archive_dir, make_feedback())

    assert first == archive_dir / "feedback-001.json"
    assert second == archive_dir / "feedback-002.json"


def test_learning_root_is_global_per_workspace(tmp_path):
    assert learning_root(tmp_path, "demo") == tmp_path / "learning" / "demo"
    store = LearningStore.for_workspace(tmp_path, "demo")
    assert store.learning_dir == tmp_path / "learning" / "demo" / "learnings"
    examples = ExampleStore.for_workspace(tmp_path, "demo")
    assert examples.examples_dir == tmp_path / "learning" / "demo"


def test_learning_store_saves_learning_with_confidence_status(tmp_path):
    store = LearningStore(tmp_path)

    path = store.save_learning(make_learning("learning-1", "pending", 0.91))

    assert path == tmp_path / "learnings" / "learning-1.json"
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

    assert path == tmp_path / "index.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    assert index["active"] == ["learning-active"]
    assert index["pending"] == ["learning-pending"]
    assert index["rejected"] == ["learning-rejected"]
    assert index["superseded"] == ["learning-superseded"]


def test_load_learnings_skips_corrupt_files_and_reports_them(tmp_path):
    store = LearningStore(tmp_path)
    store.save_learning(make_learning("learning-good", "active", 0.9))
    store.learning_dir.mkdir(parents=True, exist_ok=True)
    (store.learning_dir / "truncated.json").write_text('{"id": "tru', encoding="utf-8")
    (store.learning_dir / "not-object.json").write_text('["list"]', encoding="utf-8")
    (store.learning_dir / "missing-fields.json").write_text('{"id": "x"}', encoding="utf-8")

    learnings, skipped = store.load_learnings_with_warnings()

    assert [learning.id for learning in learnings] == ["learning-good"]
    assert sorted(skipped) == ["missing-fields.json", "not-object.json", "truncated.json"]
    # load_learnings and counts must not raise either.
    assert [learning.id for learning in store.load_learnings()] == ["learning-good"]
    assert store.counts_by_status()["active"] == 1


def test_load_learnings_tolerates_unknown_keys_and_statuses(tmp_path):
    store = LearningStore(tmp_path)
    data = make_learning("learning-odd", "active", 0.9).to_dict()
    data["status"] = "experimental"
    data["surprise_key"] = "future field"
    store.learning_dir.mkdir(parents=True, exist_ok=True)
    (store.learning_dir / "learning-odd.json").write_text(json.dumps(data), encoding="utf-8")

    learnings = store.load_learnings()
    counts = store.counts_by_status()

    assert [learning.id for learning in learnings] == ["learning-odd"]
    assert counts["experimental"] == 1
    assert counts["active"] == 0


def test_terminal_summary_includes_corrupt_file_warnings(tmp_path):
    store = LearningStore(tmp_path)
    store.save_learning(make_learning("learning-active", "active", 0.88))
    store.learning_dir.mkdir(parents=True, exist_ok=True)
    (store.learning_dir / "broken.json").write_text("{", encoding="utf-8")

    summary = store.terminal_summary()

    assert summary["active"] == 1
    assert summary["corrupt_files"] == ["broken.json"]


def test_example_store_appends_examples(tmp_path):
    store = ExampleStore(tmp_path)

    first_path = store.append_example("review", {"verdict": "FAIL"})
    second_path = store.append_example("review", {"verdict": "PASS"})

    assert first_path == tmp_path / "review.jsonl"
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

    assert path == tmp_path / "terminal-summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert summary["active"] == 1
    assert summary["pending"] == 1
    assert summary["rejected"] == 1
    assert summary["examples"] == {"learning": 1, "review": 1, "total": 2}


def test_learning_records_from_output_parses_extractor_payload():
    output = LearningOutput(
        markdown="# Learning",
        learnings=[
            {
                "rule": "Always run route tests",
                "category": "testing_pattern",
                "applies_when": "Changing API routes",
                "rationale": "A route regression slipped through",
                "confidence": 0.9,
                "tags": ["testing", 7],
                "evidence": [{"artifact": "a.md", "excerpt": "finding"}, "not-a-dict"],
                "related_files": ["src/app.py"],
            },
            {"rule": "", "category": "ignored: empty rule"},
            "not-a-dict",
            {"category": "ignored: missing rule"},
            {"rule": "Low signal", "confidence": "not-a-number"},
        ],
    )

    records = learning_records_from_output(
        output.learnings, run_id="run-9", task="Fix bug", event="pass"
    )

    assert len(records) == 2
    first = records[0]
    assert first.rule == "Always run route tests"
    assert first.id == "run-9-pass-1"
    assert first.source_run_id == "run-9"
    assert first.source_task == "Fix bug"
    assert first.confidence == 0.9
    assert first.tags == ["testing", "7"]
    assert first.evidence == [{"artifact": "a.md", "excerpt": "finding"}]
    assert first.related_files == ["src/app.py"]
    second = records[1]
    assert second.id == "run-9-pass-5"
    assert second.confidence == 0.5


def test_learning_records_round_trip_through_store(tmp_path):
    store = LearningStore(tmp_path)
    records = learning_records_from_output(
        [{"rule": "High confidence rule", "confidence": 0.95}],
        run_id="run-9",
        task="Fix bug",
        event="pass",
    )
    for record in records:
        store.save_learning(record)

    loaded = store.load_learnings()

    assert [learning.rule for learning in loaded] == ["High confidence rule"]
    assert loaded[0].status == "active"
