import json
import subprocess
import sys
from pathlib import Path

from bd1.history_loader import load_pi_history

FIXTURE = Path(__file__).parent / "fixtures" / "pi-session.jsonl"


def test_load_pi_history_returns_vet_jsonl_entries():
    entries = load_pi_history(FIXTURE)

    assert len(entries) == 2
    assert entries[0]["object_type"] == "ChatInputUserMessage"
    assert entries[0]["text"] == "Fix the bug"
    assert entries[1]["object_type"] == "ResponseBlockAgentMessage"
    assert entries[1]["role"] == "assistant"
    assert entries[1]["content"][0]["text"] == "I will inspect the code."
    assert "tests passed" not in json.dumps(entries)


def test_history_loader_cli_prints_jsonl():
    result = subprocess.run(
        [sys.executable, "-m", "bd1.history_loader", str(FIXTURE)],
        check=True,
        capture_output=True,
        text=True,
    )

    lines = result.stdout.strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["object_type"] == "ChatInputUserMessage"


def test_load_pi_history_skips_malformed_lines_with_warning(tmp_path, capsys):
    session = tmp_path / "session.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "message",
                        "message": {"role": "user", "content": "Fix the bug"},
                    }
                ),
                '{"type": "message", "message": {"role": "assistant", "conte',
                "not json at all",
                json.dumps(
                    {
                        "type": "message",
                        "id": "m-2",
                        "message": {"role": "assistant", "content": "On it."},
                    }
                ),
                json.dumps(["not", "an", "object"]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    entries = load_pi_history(session)

    assert len(entries) == 2
    assert entries[0]["text"] == "Fix the bug"
    assert entries[1]["content"][0]["text"] == "On it."
    captured = capsys.readouterr()
    assert "Skipping malformed Pi session line 2" in captured.err
    assert "Skipping malformed Pi session line 3" in captured.err


def test_load_pi_history_replaces_undecodable_bytes(tmp_path):
    session = tmp_path / "session.jsonl"
    good_line = json.dumps(
        {"type": "message", "message": {"role": "user", "content": "Fix the bug"}}
    )
    session.write_bytes(good_line.encode("utf-8") + b"\n\xff\xfe broken bytes\n")

    entries = load_pi_history(session)

    assert len(entries) == 1
    assert entries[0]["text"] == "Fix the bug"


def test_history_loader_cli_succeeds_despite_malformed_lines(tmp_path):
    session = tmp_path / "session.jsonl"
    session.write_text(
        "\n".join(
            [
                "garbage line",
                json.dumps(
                    {
                        "type": "message",
                        "message": {"role": "user", "content": "Fix the bug"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "bd1.history_loader", str(session)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["text"] == "Fix the bug"
    assert "Skipping malformed Pi session line 1" in result.stderr
