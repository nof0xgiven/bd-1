# Tech Context

## Language And Packaging

- Python `>=3.11`
- Package name: `bd-1`
- Import package: `bd1`
- Package source root: `src/`
- Package manager: `uv`
- Build backend: setuptools

## Runtime Dependencies

- `dspy-ai`
- `tomli-w`
- Python standard library modules for argparse, dataclasses, subprocess, sqlite, pathlib, JSON, and TOML loading.

## Developer Dependencies

- `pytest`
- `ruff`

## External CLI Dependencies

- Pi CLI: invoked as `pi -p <prompt> --session-id <id> --session-dir <dir>`.
- Vet CLI: invoked as `vet <task> --repo <repo> --base-commit <sha> --model <model> --history-loader <cmd> --output-format json --output <path>`.
- GitHub CLI: invoked as `gh` by default for PR create/update, checks, reviews, comments, and PR metadata.

## Entrypoints

```bash
uv run bd-1 --help
uv run bd1-pi-history-loader tests/fixtures/pi-session.jsonl
```

Installed scripts:

- `bd-1 = bd1.cli:main`
- `bd1-pi-history-loader = bd1.history_loader:main`

## Environment Variables

- `BD1_HOME`: overrides global state directory.
- `BD1_REASONING=template`: uses deterministic template reasoning for tests and fake-tool runs.

## PR Lifecycle Config

Workspace `.bd-1.toml` includes:

```toml
pr_command = "gh"
pr_monitor_wait_seconds = 600
max_pr_feedback_attempts = 3
pr_base_branch = ""
pr_draft = false
```

Use `pr_monitor_wait_seconds = 0` only for tests or controlled smoke runs.

## Standard Verification Commands

```bash
uv run ruff format src tests
uv run ruff check src tests
uv run pytest -q
uv run bd-1 --help
uv run bd1-pi-history-loader tests/fixtures/pi-session.jsonl
vet "history loader contract check" \
  --repo . \
  --base-commit HEAD \
  --model flash \
  --history-loader "uv run bd1-pi-history-loader tests/fixtures/pi-session.jsonl" \
  --output-format json \
  --output /tmp/bd1-vet-history-contract.json
```

## Testing Notes

- Unit tests use fakes for Pi, Vet, PR, setup runner, and reasoning programs.
- CLI E2E creates real temporary git repos and fake `pi`, `vet`, and `gh` executables on PATH.
- History loader tests use `tests/fixtures/pi-session.jsonl`.
- Live smoke testing can be run against `ava-realtime` using a fresh `BD1_HOME`.

## Constraints

- The direct `bd-1` command may not be installed globally. Prefer `uv run bd-1` inside this repo.
- Live DSPy reasoning requires model/API configuration.
- PR lifecycle requires `gh` authentication and repository/remote permissions at runtime.
- Vet should use `--model flash` unless the user says otherwise.
- Do not depend on raw `.sessions/` or SQLite as durable committed state.
