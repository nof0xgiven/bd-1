import json
from pathlib import Path

import pytest

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
        ".artifacts/pr",
        ".artifacts/blockers",
        ".artifacts/learning",
        ".sessions",
    ]:
        assert (tmp_path / relative).is_dir()

    # Learnings and examples live in the global store under BD1_HOME, not the repo.
    assert not (tmp_path / ".learning").exists()
    assert not (tmp_path / ".examples").exists()


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


def test_redaction_removes_authorization_scheme_credentials():
    text = (
        "Authorization: Basic dXNlcjpwYXNz\n"
        "Authorization: token ghp_abcdefghijklmnopqrstu012345\n"
        "Authorization: Bearer token123\n"
        '"Authorization": "Basic dXNlcjpwYXNz"\n'
    )

    redacted = redact_text(text)

    assert "dXNlcjpwYXNz" not in redacted
    assert "ghp_abcdefghijklmnopqrstu012345" not in redacted
    assert "token123" not in redacted
    assert "[REDACTED]" in redacted


def test_redaction_removes_standalone_token_shapes():
    text = "\n".join(
        [
            "github token ghp_ABCDEFGHIJKLMNOPQRSTuvwxyz0123",
            "fine grained github_pat_11ABCDEFGHIJKLMNOPQRST_more",
            "openai sk-proj-ABCDEFGHIJKLMNOPQRSTuvwxyz",
            "aws AKIAIOSFODNN7EXAMPLE",
            "slack xoxb-1234567890-abcdefghij",
        ]
    )

    redacted = redact_text(text)

    assert "ghp_ABCDEFGHIJKLMNOPQRSTuvwxyz0123" not in redacted
    assert "github_pat_11ABCDEFGHIJKLMNOPQRST_more" not in redacted
    assert "sk-proj-ABCDEFGHIJKLMNOPQRSTuvwxyz" not in redacted
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "xoxb-1234567890-abcdefghij" not in redacted
    assert redacted.count("[REDACTED]") == 5


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


def test_write_text_replaces_target_atomically_via_same_dir_temp_file(tmp_path, monkeypatch):
    import os as os_module

    import bd1.artifacts as artifacts_module

    calls = []
    real_replace = os_module.replace

    def spy_replace(source, destination):
        calls.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(artifacts_module.os, "replace", spy_replace)
    target = tmp_path / "x.md"
    target.write_text("old\n", encoding="utf-8")

    write_text(target, "new\n", redact=False)

    source, destination = calls[0]
    assert destination == target
    assert source != target
    assert source.parent == target.parent
    assert not source.exists()
    assert target.read_text(encoding="utf-8") == "new\n"
    assert list(tmp_path.iterdir()) == [target]


def test_write_text_leaves_no_temp_file_when_write_fails(tmp_path, monkeypatch):
    import bd1.artifacts as artifacts_module

    def broken_replace(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(artifacts_module.os, "replace", broken_replace)
    target = tmp_path / "x.md"
    target.write_text("old\n", encoding="utf-8")

    with pytest.raises(OSError):
        write_text(target, "new\n", redact=False)

    assert target.read_text(encoding="utf-8") == "old\n"
    assert list(tmp_path.iterdir()) == [target]
