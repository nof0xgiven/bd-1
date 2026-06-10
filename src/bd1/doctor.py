from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIN_GH_VERSION = (2, 59, 0)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def gh_version_ok(version_output: str) -> bool:
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", version_output)
    if not match:
        return False
    return tuple(int(part) for part in match.groups()) >= MIN_GH_VERSION


def run_checks(
    *,
    binaries: tuple[str, ...],
    which: Callable[[str], str | None] | None = None,
    runner: Any = None,
    dspy_model: str = "",
) -> list[CheckResult]:
    # `which` is late-bound so tests can monkeypatch shutil.which; a default
    # argument would freeze the original function at import time.
    active_which = which or shutil.which
    results: list[CheckResult] = []
    for binary in binaries:
        path = active_which(binary)
        if path:
            results.append(CheckResult(f"binary:{binary}", True, path))
        else:
            results.append(CheckResult(f"binary:{binary}", False, f"{binary} not found on PATH"))
    gh_binary = next((binary for binary in binaries if Path(binary).name == "gh"), None)
    gh_present = gh_binary is not None and any(
        result.name == f"binary:{gh_binary}" and result.ok for result in results
    )
    if gh_present and runner is not None:
        # A diagnostic tool should always finish its diagnosis: a broken gh
        # binary becomes a failed check, never an aborted run.
        try:
            version = runner([gh_binary, "--version"], cwd=".", timeout=30)
        except Exception as exc:
            results.append(CheckResult("gh:version", False, str(exc)))
        else:
            ok = version.exit_code == 0 and gh_version_ok(version.stdout)
            output = version.stdout or version.stderr
            results.append(CheckResult("gh:version", ok, output.splitlines()[0] if output else ""))
    results.append(
        CheckResult(
            "dspy_model",
            bool(dspy_model.strip()),
            dspy_model.strip() or "dspy_model is empty in .bd-1.toml",
        )
    )
    return results
