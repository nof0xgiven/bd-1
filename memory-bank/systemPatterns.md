# System Patterns

## Architecture Shape

bd-1 separates execution, verification, review, and learning.

- Pi performs code changes in a task worktree.
- Vet independently checks the task, diff, and Pi transcript.
- GitHub CLI publishing and monitoring runs after local review passes.
- DSPy programs generate discovery, plans, review decisions, and learning content. Discovery is a `dspy.ReAct` agent over sandboxed read-only repo tools (`src/bd1/repo_tools.py`) with a single-shot fallback; profiling is agentic with a keyword fallback and visible degradation warnings.
- RunStore writes authoritative run records to files.
- RunIndex mirrors run records into SQLite for lookup.

## Main Components

### CLI

File: `src/bd1/cli.py`

Commands:

- `workspace add` (supports `--profile {agentic,keyword}`)
- `workspace list`
- `workspace profile` (supports `--profile {agentic,keyword}`)
- `run`
- `status`
- `clean` (archives the full learning corpus, then removes worktree and branch)
- `feedback`
- `doctor` (binaries, `gh` >= 2.59, `dspy_model`)
- `sync` (merge-triggered learning by polling `gh pr view`)

Workspace resolution order:

1. Explicit `--workspace`.
2. Current directory or parent `.bd-1.toml`.
3. Sole registered workspace.
4. Error with available workspace names.

### Orchestrator

File: `src/bd1/orchestrator.py`

Responsibilities:

- Preflight required executables (full diagnosis lives in `bd-1 doctor`).
- Verify clean base repo.
- Create task branch and worktree.
- Apply task-runtime git excludes.
- Write run records and transitions.
- Generate discovery and plan artifacts.
- Invoke Pi.
- Enforce clean committed execution.
- Invoke Vet.
- Run review.
- Publish or update the PR after `REVIEW_PASSED`.
- Monitor PR checks and actionable feedback.
- Loop PR feedback back to Pi.
- Record completion, blockers, and learning.

### Subprocess Adapters

Files:

- `src/bd1/pi.py`
- `src/bd1/pr.py`
- `src/bd1/vet.py`
- `src/bd1/setup_runner.py`
- `src/bd1/subprocesses.py`

Adapters preserve commands, exit codes, stdout, stderr, and artifact paths. They should not hide failures behind synthetic success. `src/bd1/pr.py` wraps `git push` and `gh` PR commands, translates startup and command failures into controlled PR errors, and writes PR lifecycle artifacts.

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

Artifacts are redacted on write unless explicitly disabled. Workspace setup creates `.artifacts/` and `.sessions/` directories. Learnings and DSPy examples live in the global store under `<BD1_HOME>/learning/<workspace>/` so they survive worktree cleanup.

## State Machine

Implemented states and the legal-transition table (`ALLOWED_TRANSITIONS`) are in
`src/bd1/models.py`; `RunStore.transition` rejects any jump not in the table.

Important happy path:

`TASK_RECEIVED -> BASE_VERIFIED -> WORKTREE_CREATED -> DISCOVERY_COMPLETE -> PLAN_COMPLETE -> EXECUTION_PROMPT_READY -> EXECUTION_RUNNING -> EXECUTION_COMMITTED -> VET_PASSED -> REVIEW_RUNNING -> REVIEW_PASSED -> PR_PUBLISHING -> PR_CREATED -> PR_MONITORING -> PR_READY -> COMPLETE`

Important failure paths:

- Dirty base repo raises before worktree creation.
- Setup failure writes a blocker.
- Missing Pi session writes a blocker before Vet.
- Dirty task worktree prompts Pi again with `commit and resolve before exit`.
- Repeated Vet findings loop until max attempts, then block.
- Review failure loops back to Pi with a revision prompt.
- PR check, CodeRabbit, or human review feedback writes `.artifacts/pr/` feedback and loops back to Pi.
- Repeated PR feedback blocks after `max_pr_feedback_attempts`; PR feedback rounds do not consume the `max_attempts` execution budget.
- Unexpected exceptions raised after the run record exists land the run in BLOCKED with the traceback in the blocker artifact.
- Merge conflicts get a focused fetch-first conflict prompt separated from other feedback; unknown mergeability surfaces as PR feedback or blocker conditions. Merge automation is not implemented; post-merge learning is `bd-1 sync` polling.

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
- `.artifacts/pr/`
- `.artifacts/learning/`
- `*.db`
- `*.sqlite`
