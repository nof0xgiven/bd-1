import json

from bd1.artifacts import (
    ensure_global_dirs,
    ensure_workspace_dirs,
    redact_text,
    write_json,
    write_text,
)


def test_workspace_dirs_include_full_storage_contract(tmp_path):
    ensure_workspace_dirs(tmp_path)

    for relative in [
        ".artifacts/context",
        ".artifacts/plans",
        ".artifacts/completed",
        ".artifacts/vet",
        ".artifacts/reviews",
        ".artifacts/blockers",
        ".artifacts/learning",
        ".learning/learnings",
        ".examples",
        ".sessions",
    ]:
        assert (tmp_path / relative).is_dir()


def test_global_dirs_include_full_storage_contract(tmp_path):
    ensure_global_dirs(tmp_path)

    for relative in ["runs", "compiled-dspy", "logs", "worktrees"]:
        assert (tmp_path / relative).is_dir()


def test_redaction_covers_common_secret_shapes():
    text = (
        "OPENAI_API_KEY=sk-secret\n"
        "Authorization: Bearer token123\n"
        "DATABASE_URL=postgres://user:pass@host/db"
    )

    redacted = redact_text(text)

    assert "sk-secret" not in redacted
    assert "token123" not in redacted
    assert "postgres://user:pass@host/db" not in redacted
    assert "[REDACTED]" in redacted


def test_write_text_redacts_by_default(tmp_path):
    path = write_text(tmp_path / ".artifacts" / "x.md", "TOKEN=abc123")

    assert "abc123" not in path.read_text(encoding="utf-8")


def test_write_json_can_redact(tmp_path):
    path = write_json(tmp_path / ".artifacts" / "x.json", {"token": "abc123"}, redact=True)
    content = path.read_text(encoding="utf-8")

    assert "abc123" not in content
    assert json.loads(content) == {"token": "[REDACTED]"}


def test_write_json_redaction_does_not_treat_passed_as_secret(tmp_path):
    path = write_json(tmp_path / ".artifacts" / "x.json", {"passed": True}, redact=True)

    assert json.loads(path.read_text(encoding="utf-8")) == {"passed": True}


def test_write_json_redacts_non_string_secret_values_without_breaking_json(tmp_path):
    path = write_json(
        tmp_path / ".artifacts" / "x.json",
        {"token": 123, "metadata": {"database_url": None}},
        redact=True,
    )

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "metadata": {"database_url": "[REDACTED]"},
        "token": "[REDACTED]",
    }
