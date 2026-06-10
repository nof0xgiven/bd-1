from __future__ import annotations

import re
from pathlib import Path

MAX_READ_BYTES = 24_000
MAX_TREE_ENTRIES = 400
MAX_SEARCH_RESULTS = 50
SKIP_DIRS = {".git", ".sessions", "node_modules", "__pycache__", ".venv", "venv"}
# These tools feed file content to an LM: never read likely secret material.
SECRET_NAME_RE = re.compile(
    r"(^\.env($|\.)|\.pem$|\.key$|^id_rsa|^id_ed25519|^id_ecdsa|^secrets?\.)",
    re.IGNORECASE,
)


class RepoTools:
    """Read-only, sandboxed repository access for reasoning agents.

    Every method returns a plain string (never raises) so it can be used
    directly as a DSPy ReAct tool: errors become observations the model
    can react to.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def list_tree(self, subdir: str = "") -> str:
        """List repository files (relative paths), skipping VCS/dependency dirs."""
        base = self._resolve(subdir)
        if base is None:
            return f"error: path escapes the repository: {subdir}"
        entries: list[str] = []
        for path in sorted(base.rglob("*")):
            # Judge skip-dirs by repo-RELATIVE parts: an absolute parent named
            # "build" or "tmp" must not blank out the entire repository.
            if any(part in SKIP_DIRS for part in path.relative_to(self.root).parts):
                continue
            if path.is_file():
                entries.append(path.relative_to(self.root).as_posix())
            if len(entries) >= MAX_TREE_ENTRIES:
                entries.append(f"... truncated at {MAX_TREE_ENTRIES} entries")
                break
        return "\n".join(entries) if entries else "no files found"

    def read_file(self, relative_path: str, start_line: int = 1) -> str:
        """Read a file with line numbers, starting at start_line, capped in size."""
        path = self._resolve(relative_path)
        if path is None:
            return f"error: path escapes the repository: {relative_path}"
        if not path.is_file():
            return f"error: not a file: {relative_path}"
        if SECRET_NAME_RE.search(path.name):
            return f"error: refusing to read potential secret file: {relative_path}"
        try:
            begin = max(1, int(start_line))
        except (TypeError, ValueError):
            return f"error: invalid start_line: {start_line!r}"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"error: unable to read {relative_path}: {exc}"
        lines = text.splitlines()
        numbered = [f"{index}: {line}" for index, line in enumerate(lines, 1)][begin - 1 :]
        out: list[str] = []
        used = 0
        for line in numbered:
            used += len(line) + 1
            if used > MAX_READ_BYTES:
                out.append(f"... truncated; continue with start_line={begin + len(out)}")
                break
            out.append(line)
        return "\n".join(out) if out else "error: empty file"

    def search_text(self, pattern: str, glob: str = "") -> str:
        """Regex search across repository files; returns path:line: text matches."""
        try:
            compiled = re.compile(pattern)
        except (re.error, TypeError) as exc:
            return f"error: invalid regex: {exc}"
        try:
            paths = sorted(self.root.rglob(glob or "*"))
        except (ValueError, NotImplementedError, TypeError, OSError) as exc:
            return f"error: invalid glob: {exc}"
        results: list[str] = []
        for path in paths:
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(self.root).parts):
                continue
            if SECRET_NAME_RE.search(path.name):
                continue
            # Symlinks must not smuggle content from outside the sandbox (or
            # from secret-named targets) into search results.
            try:
                real = path.resolve()
            except OSError:
                continue
            if real != self.root and self.root not in real.parents:
                continue
            if SECRET_NAME_RE.search(real.name):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line_number, line in enumerate(text.splitlines(), 1):
                if compiled.search(line):
                    relative = path.relative_to(self.root).as_posix()
                    results.append(f"{relative}:{line_number}: {line.strip()[:200]}")
                    if len(results) >= MAX_SEARCH_RESULTS:
                        results.append(f"... truncated at {MAX_SEARCH_RESULTS} matches")
                        return "\n".join(results)
        return "\n".join(results) if results else "no matches"

    def _resolve(self, relative: str) -> Path | None:
        try:
            candidate = (self.root / relative).resolve() if relative else self.root
        except (TypeError, ValueError, OSError):
            return None
        if candidate != self.root and self.root not in candidate.parents:
            return None
        if any(part in SKIP_DIRS for part in candidate.relative_to(self.root).parts):
            return None
        return candidate
