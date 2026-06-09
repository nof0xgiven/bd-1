from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load_pi_history(session_file: str | Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in Path(session_file).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("type") != "message":
            continue

        message = event.get("message") or {}
        role = str(message.get("role") or "")
        if role == "toolResult":
            continue
        text = _extract_text(message.get("content"))
        if not text:
            continue

        if role == "user":
            entries.append({"object_type": "ChatInputUserMessage", "text": text})
        else:
            entries.append(
                {
                    "object_type": "ResponseBlockAgentMessage",
                    "role": "assistant" if role == "assistant" else "system",
                    "assistant_message_id": _assistant_message_id(event.get("id")),
                    "content": [
                        {
                            "object_type": "TextBlock",
                            "type": "text",
                            "text": text,
                        }
                    ],
                }
            )
    return entries


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return json.dumps(content, sort_keys=True)


def _assistant_message_id(raw_id: Any) -> str:
    value = str(raw_id or "message")
    return value if value.startswith("asst-") else f"asst-{value}"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: bd1-pi-history-loader <session-jsonl>", file=sys.stderr)
        return 2

    try:
        entries = load_pi_history(args[0])
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid Pi session JSONL: {exc}", file=sys.stderr)
        return 1

    for entry in entries:
        print(json.dumps(entry, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
