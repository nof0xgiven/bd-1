# System Patterns

## Architecture Shape

bd-1 separates execution, verification, review, and learning.

- Pi performs code changes in a task worktree.
- Vet independently checks the task, diff, and Pi transcript.
- DSPy programs generate discovery, plans, review decisions, and learning content.
- RunStore writes authoritative run records to files.
- RunIndex mirrors run records into SQLite for lookup.

## Main Components

### CLI

File: `src/bd1/cli.py`

Commands:

- `workspace add`
- `workspace list`
- `workspace profile`
- `run`
- `status`
- `feedback`

Workspace resolution order:

1. Explicit `--workspace`.
2. Current directory or parent `.bd-1.toml`.
3. Sole registered workspace.
4. Error with available workspace names.

### Orchestrator

File: `src/bd1/orchestrator.py`

Responsibilities:

- Verify clean base repo.
- Create task branch and worktree.
- Apply task-runtime git excludes.
- Write run records and transitions.
- Generate discovery and plan artifacts.
- Invoke Pi.
- Enforce clean committed execution.
- Invoke Vet.
- Run review.
- Record completion, blockers, and learning.

### Subprocess Adapters

Files:

- `src/bd1/pi.py`
- `src/bd1/vet.py`
- `src/bd1/setup_runner.py`
- `src/bd1/subprocesses.py`

Adapters preserve commands, exit codes, stdout, stderr, and artifact paths. They should not hide failures behind synthetic success.

### Stores

Files:

- `src/bd1/run_store.py`
- `src/bd1/run_index.py`
- `src/bd1/registry.py`
- `src/bd1/learning.py`
- `src/bd1/feedback.py`

Run records live under `.sessions/<run-id>/run-record.json`. Global pointers live under `<BD1_HOME>/runs/<run-id>.json`. SQLite lives at `<BD1_HOME>/runs.db`.

### Artifacts

File: `src/bd1/artifacts.py`

Artifacts are redacted on write unless explicitly disabled. Workspace setup creates `.artifacts/`, `.learning/`, `.examples/`, and `.sessions/` directories.

## State Machine

Implemented states are in `src/bd1/models.py`.

Important happy path:

`TASK_RECEIVED -> BASE_VERIFIED -> WORKTREE_CREATED -> DISCOVERY_COMPLETE -> PLAN_COMPLETE -> EXECUTION_PROMPT_READY -> EXECUTION_RUNNING -> EXECUTION_COMMITTED -> VET_PASSED -> REVIEW_RUNNING -> REVIEW_PASSED -> COMPLETE`

Important failure paths:

- Dirty base repo raises before worktree creation.
- Setup failure writes a blocker.
- Missing Pi session writes a blocker before Vet.
- Dirty task worktree prompts Pi again with `commit and resolve before exit`.
- Repeated Vet findings loop until max attempts, then block.
- Review failure loops back to Pi with a revision prompt.

## Runtime Ignore Pattern

Task worktrees use worktree-specific `core.excludesFile` so runtime files do not dirty completed task branches.

Runtime excludes include:

- `.sessions/`
- `.artifacts/context/`
- `.artifacts/plans/`
- `.artifacts/vet/`
- `.artifacts/reviews/`
- `.artifacts/blockers/`
- `.artifacts/completed/`
- `.artifacts/learning/`
- `.examples/`
- `*.db`
- `*.sqlite`

The source workspace can still track curated `.examples/` files.
