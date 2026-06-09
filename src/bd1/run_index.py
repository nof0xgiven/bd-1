from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from bd1.models import RunRecord


class RunIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    workspace TEXT NOT NULL,
                    task TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def upsert_run(self, record: RunRecord) -> None:
        payload = json.dumps(record.to_dict(), sort_keys=True)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO runs (run_id, workspace, task, state, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    workspace = excluded.workspace,
                    task = excluded.task,
                    state = excluded.state,
                    payload = excluded.payload
                """,
                (record.run_id, record.workspace, record.task, record.state.value, payload),
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunRecord.from_dict(json.loads(row[0]))

    def rebuild_from_workspace(self, repo_path: str | Path) -> None:
        sessions_dir = Path(repo_path) / ".sessions"
        for record_path in sorted(sessions_dir.glob("*/run-record.json")):
            record = RunRecord.from_dict(json.loads(record_path.read_text(encoding="utf-8")))
            self.upsert_run(record)
