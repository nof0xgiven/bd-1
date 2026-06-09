from __future__ import annotations

import json
from pathlib import Path

from bd1.errors import WorkspaceConfigError
from bd1.models import WorkspaceConfig


class WorkspaceRegistry:
    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "workspaces.json"

    def add(self, config: WorkspaceConfig) -> None:
        workspaces = self._load()
        workspaces[config.name] = config.to_dict()
        self._write(workspaces)

    def get(self, name: str) -> WorkspaceConfig:
        workspaces = self._load()
        try:
            data = workspaces[name]
        except KeyError as exc:
            raise WorkspaceConfigError(f"Workspace is not registered: {name}") from exc
        return WorkspaceConfig.from_dict(data)

    def list_workspaces(self) -> list[WorkspaceConfig]:
        workspaces = self._load()
        return [WorkspaceConfig.from_dict(workspaces[name]) for name in sorted(workspaces)]

    def _load(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, workspaces: dict[str, dict[str, object]]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(workspaces, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
