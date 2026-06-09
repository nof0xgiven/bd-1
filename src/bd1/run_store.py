from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from bd1.artifacts import write_json
from bd1.models import RunRecord, RunState
from bd1.paths import global_state_dir


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RunStore:
    def __init__(self, global_root: str | Path | None = None) -> None:
        self.global_root = Path(global_root) if global_root else global_state_dir()
        (self.global_root / "runs").mkdir(parents=True, exist_ok=True)

    def write(self, repo_path: str | Path, record: RunRecord) -> Path:
        path = Path(repo_path) / ".sessions" / record.run_id / "run-record.json"
        write_json(path, record.to_dict(), redact=False)

        pointer = {"workspace": record.workspace, "run_record_path": str(path)}
        write_json(self.global_root / "runs" / f"{record.run_id}.json", pointer, redact=False)
        return path

    def read(self, path: str | Path) -> RunRecord:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return RunRecord.from_dict(data)

    def read_by_id(self, run_id: str) -> RunRecord:
        pointer_path = self.global_root / "runs" / f"{run_id}.json"
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        return self.read(pointer["run_record_path"])

    def transition(
        self,
        repo_path: str | Path,
        record: RunRecord,
        state: RunState,
        reason: str,
    ) -> RunRecord:
        updated_at = max(now_iso(), record.updated_at)
        updated = replace(record, state=state, updated_at=updated_at)
        self.write(repo_path, updated)

        transition_path = Path(repo_path) / ".sessions" / record.run_id / "transitions.jsonl"
        transition_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"state": state.value, "reason": reason, "at": updated.updated_at}
        with transition_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return updated
