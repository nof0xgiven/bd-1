from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from bd1.artifacts import write_json
from bd1.errors import IllegalTransitionError, UnknownRunError
from bd1.models import ALLOWED_TRANSITIONS, RunRecord, RunState
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

    def archive_dir(self, run_id: str) -> Path:
        return self.global_root / "runs" / run_id

    def archive(self, record: RunRecord) -> Path:
        archive_dir = self.archive_dir(record.run_id)
        archive_dir.mkdir(parents=True, exist_ok=True)
        session_dir = Path(record.worktree) / ".sessions" / record.run_id
        for name in ("run-record.json", "transitions.jsonl"):
            source = session_dir / name
            if source.is_file():
                shutil.copy2(source, archive_dir / name)
        record_path = archive_dir / "run-record.json"
        if not record_path.exists():
            write_json(record_path, record.to_dict(), redact=False)
        pointer = {"workspace": record.workspace, "run_record_path": str(record_path)}
        write_json(self.global_root / "runs" / f"{record.run_id}.json", pointer, redact=False)
        return record_path

    def write_archived(self, record: RunRecord) -> Path:
        """Persist an updated record into the archive when the worktree is gone."""
        archive_dir = self.archive_dir(record.run_id)
        path = write_json(archive_dir / "run-record.json", record.to_dict(), redact=False)
        pointer = {"workspace": record.workspace, "run_record_path": str(path)}
        write_json(self.global_root / "runs" / f"{record.run_id}.json", pointer, redact=False)
        return path

    def read_by_id(self, run_id: str) -> RunRecord:
        pointer_path = self.global_root / "runs" / f"{run_id}.json"
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise UnknownRunError(f"Unknown run id: {run_id}") from exc
        except json.JSONDecodeError as exc:
            raise UnknownRunError(f"Corrupt run pointer for {run_id}: {pointer_path}") from exc

        record_path = Path(str(pointer["run_record_path"]))
        archived_path = self.archive_dir(run_id) / "run-record.json"
        for candidate in (record_path, archived_path):
            try:
                return self.read(candidate)
            except FileNotFoundError:
                continue
            except json.JSONDecodeError as exc:
                raise UnknownRunError(f"Corrupt run record for {run_id}: {candidate}") from exc
        raise UnknownRunError(
            f"Run record for {run_id} not found (worktree may have been removed): {record_path}"
        )

    def transition(
        self,
        repo_path: str | Path,
        record: RunRecord,
        state: RunState,
        reason: str,
    ) -> RunRecord:
        allowed = ALLOWED_TRANSITIONS.get(record.state, frozenset())
        if state not in allowed:
            raise IllegalTransitionError(
                f"Illegal state transition for run {record.run_id}: "
                f"{record.state.value} -> {state.value}"
            )
        updated_at = max(now_iso(), record.updated_at, key=_parse_iso)
        updated = replace(record, state=state, updated_at=updated_at)
        self.write(repo_path, updated)

        transition_path = Path(repo_path) / ".sessions" / record.run_id / "transitions.jsonl"
        transition_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"state": state.value, "reason": reason, "at": updated.updated_at}
        with transition_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return updated


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
