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
