# bd-1

`bd-1` is a local CLI for running a coding task through an isolated worktree, Pi execution, Vet verification, a review gate, and learning capture.

The current MVP is Python + uv. Files are authoritative: each run writes `.sessions/<run-id>/run-record.json` in the task worktree, while the global SQLite database under `~/.bd-1` acts as a rebuildable index.

## Install

```bash
uv sync
uv run bd-1 --help
```

After packaging or installing the project, use `bd-1` directly instead of `uv run bd-1`.

## Register a workspace

Run this from the bd-1 repo or anywhere with the CLI available:

```bash
uv run bd-1 workspace add \
  --name ava-realtime \
  --repo /Users/ava/main/projects/ava-realtime \
  --product "Realtime LiveKit/Runway/Gemini/OpenAI avatar workspace"
```

The command writes `.bd-1.toml` plus profile artifacts under `.artifacts/`. Review and commit the generated workspace files before running tasks:

```bash
git -C /Users/ava/main/projects/ava-realtime add .bd-1.toml .artifacts .learning .examples
git -C /Users/ava/main/projects/ava-realtime commit -m "chore: add bd-1 workspace artifacts"
```

`bd-1` refuses to create a task worktree from a dirty base repo. Check first:

```bash
git -C /Users/ava/main/projects/ava-realtime status --short
```

## Run a task

From inside a registered repo, `bd-1 run` resolves `.bd-1.toml` automatically:

```bash
uv run bd-1 run "Make a small scoped change"
```

From another directory, pass the workspace name:

```bash
uv run bd-1 run --workspace ava-realtime "Make a small scoped change"
```

Runtime flow:

1. Verify the base repo is clean.
2. Create a task worktree under `~/.bd-1/worktrees/<workspace>/<run-id>`.
3. Build discovery and plan artifacts.
4. Invoke Pi with a fixed session id and session dir.
5. Run Vet with `bd1-pi-history-loader`.
6. Run the review gate.
7. Save completion, blocker, review, and learning artifacts.

## Inspect runs

Print the authoritative run record and refresh the SQLite index:

```bash
uv run bd-1 status <run-id>
```

Add correction feedback and capture a learning event:

```bash
uv run bd-1 feedback <run-id> \
  --outcome wrong_behavior \
  --wrong-or-missing "What bd-1 missed" \
  --expected "What should happen next time"
```

## Runtime files

Workspace setup creates durable, reviewable files:

```text
.bd-1.toml
.artifacts/architecture.md
.artifacts/system-patterns.md
.artifacts/testing.md
.artifacts/design.md
.artifacts/rules.md
.artifacts/product.md
.learning/
.examples/
```

Raw run state and rebuildable caches stay out of normal commits:

```text
.sessions/
*.db
*.sqlite
```

Task worktrees also ignore runtime artifact subdirectories such as `.artifacts/context/`, `.artifacts/plans/`, `.artifacts/reviews/`, `.artifacts/completed/`, `.artifacts/blockers/`, and `.artifacts/learning/`.

## Reasoning mode

By default, bd-1 uses live DSPy programs with the model configured in `.bd-1.toml`.

Tests use deterministic template reasoning:

```bash
BD1_REASONING=template uv run bd-1 run "Make a fixture change"
```

Use template mode only for local tests and fake-tool E2E runs.

## Verification

Run the local checks:

```bash
uv run ruff format src tests
uv run ruff check src tests
uv run pytest -q
uv run bd1-pi-history-loader tests/fixtures/pi-session.jsonl
vet "history loader contract check" \
  --repo . \
  --base-commit HEAD \
  --model flash \
  --history-loader "uv run bd1-pi-history-loader tests/fixtures/pi-session.jsonl" \
  --output-format json \
  --output /tmp/bd1-vet-history-contract.json
```
