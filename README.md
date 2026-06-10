# bd-1

<p align="center">
  <img src="assets/hero.png" alt="A glowing orbital loop passing through five gates — discover, plan, execute, verify, merge — feeding a crystalline memory core at its center" width="100%">
</p>

`bd-1` is a local CLI for running a coding task through an isolated worktree, Pi execution, Vet verification, a review gate, PR feedback, and learning capture. Every run feeds a durable learning store that the next run inherits — each unit of work makes the next one easier.

The current MVP is Python + uv. Files are authoritative: each run writes `.sessions/<run-id>/run-record.json` in the task worktree, while the global SQLite database under `~/.bd-1` acts as a rebuildable index.

## Install

```bash
uv sync
uv run bd-1 --help
```

After packaging or installing the project, use `bd-1` directly instead of `uv run bd-1`.

The PR lifecycle requires GitHub CLI `gh` (>= 2.59) installed, authenticated, and authorized for the target repository.

Check the environment before running tasks:

```bash
uv run bd-1 doctor --workspace your-app
```

`bd-1 doctor` verifies the configured binaries (`git`, `pi`, `vet`, `gh`), the `gh` version (>= 2.59), and that `dspy_model` is configured. `bd-1 run` repeats the binary-presence part of this preflight before touching the repo and refuses to start when an executable is missing.

## Register a workspace

Run this from the bd-1 repo or anywhere with the CLI available:

```bash
uv run bd-1 workspace add \
  --name your-app \
  --repo /path/to/your-app \
  --product "Realtime LiveKit/Runway/Gemini/OpenAI avatar workspace"
```

The command writes `.bd-1.toml` plus profile artifacts under `.artifacts/`. Profiling is agentic by default: a DSPy `ProfileWorkspace` program reads capped, text-only repo evidence and writes the profile docs. If the agentic path is unavailable (no `dspy_model`, construction failure), bd-1 degrades to the keyword fallback and prints a visible warning plus a `.artifacts/` warning file. Force a mode with `--profile {agentic,keyword}` on both `workspace add` and `workspace profile`:

```bash
uv run bd-1 workspace profile your-app --profile keyword
```

Review and commit the generated workspace files before running tasks:

```bash
git -C /path/to/your-app add .bd-1.toml .artifacts
git -C /path/to/your-app commit -m "chore: add bd-1 workspace artifacts"
```

`bd-1` refuses to create a task worktree from a dirty base repo. Check first:

```bash
git -C /path/to/your-app status --short
```

## Run a task

From inside a registered repo, `bd-1 run` resolves `.bd-1.toml` automatically:

```bash
uv run bd-1 run "Make a small scoped change"
```

From another directory, pass the workspace name:

```bash
uv run bd-1 run --workspace your-app "Make a small scoped change"
```

Runtime flow:

1. Preflight: verify the required executables exist (run `bd-1 doctor` for the full diagnosis).
2. Verify the base repo is clean.
3. Create a task worktree under `~/.bd-1/worktrees/<workspace>/<run-id>`.
4. Run tool-using discovery: a `dspy.ReAct` agent explores the repo through sandboxed read-only tools, with a diagnosable single-shot fallback. Then build the plan artifact.
5. Invoke Pi with a fixed session id and session dir under an executor contract (TDD, no mocks of the system under test, proof-of-work completion summary).
6. Run Vet with `bd1-pi-history-loader`.
7. Run the review gate. The verdict is binary `PASS`/`FAIL`; any P1 or P2 finding forces `FAIL` and loops back to execution with a revision prompt.
8. Push the task branch and create or update the PR. The executor's completion summary flows into the review and the PR body.
9. Wait for the configured PR monitor delay.
10. Capture CI/check failures and actionable PR review feedback. Merge conflicts get a focused fetch-first conflict prompt that separates conflict resolution from other feedback.
11. Loop back to Pi when PR feedback requires changes.
12. Save completion, PR, blocker, review, and learning artifacts.

## Where the prompts live

There is no prompt directory; the live prompts ship in code:

- **Reasoning instructions** (discovery, planning, review, learning, profiling) are DSPy signature docstrings and field descriptions in `src/bd1/dspy_programs.py`. They are seed instructions: DSPy optimizers can tune them later, so they stay tight and declarative.
- **Coding-agent contracts** (executor, revision, merge-conflict resolution) are the `compile_*_prompt` functions in `src/bd1/orchestrator.py`.

Editing those docstrings, field descriptions, and `compile_*_prompt` functions is the supported way to customize bd-1's behavior.

## External research tools (MCP)

Discovery can call external research tools (code search, library docs) through any stdio MCP server. The knob is `discovery_mcp_servers` in `.bd-1.toml`: a list of shell-style command strings, one per server. Default is empty — out-of-the-box runs make zero network calls.

Two free servers that restore the original design's external research leg:

```toml
discovery_mcp_servers = ["npx -y exa-mcp-server", "npx -y @upstash/context7-mcp"]
```

- **Exa** (code/web search) needs `EXA_API_KEY` in the environment (free tier available).
- **Context7** (library docs) works keyless.
- Both require Node (`npx`).

The configured server commands are executed with your privileges — the same trust level as `setup_script` and `pi_command` — so only list servers you trust.

Failures degrade gracefully: a server that fails to start (or hangs past a 20s startup timeout) is skipped with a stderr warning, and discovery continues with the repo tools.

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

## Clean up runs

`bd-1 clean` archives a finished (`COMPLETE` or `BLOCKED`) run, then removes its task worktree and branch:

```bash
uv run bd-1 clean <run-id>
```

Before anything is deleted, the full learning corpus is copied to `~/.bd-1/runs/<run-id>/`:

```text
run-record.json
transitions.jsonl
final-diff.patch
review.md
pi-session.jsonl
pi-stdout.txt
pi-stderr.txt
vet-output.json
discovery-context.md
plan.md
completed.md
pr-feedback-001.md (one per PR feedback round)
```

`bd-1 status` and `bd-1 sync` keep working against the archive after the worktree is gone.

## Merge-triggered learning

`bd-1 sync` checks each archived run's PR via `gh pr view`; when a PR has merged since the last sync, it extracts learnings from the archived corpus into the global learning store and stamps `merge_synced_at` so each merge is learned from exactly once:

```bash
uv run bd-1 sync                      # sweep all workspaces
uv run bd-1 sync --workspace your-app
```

The output is a JSON summary (`checked`, `learned`, `skipped`). Unreachable PRs, stale records, and deregistered workspaces are reported in `skipped` without aborting the sweep. There is no webhook listener yet: run `bd-1 sync` periodically (cron or CI) until webhook support lands.

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
```

Learnings and DSPy examples are stored globally under `<BD1_HOME>/learning/<workspace>/`
(default `~/.bd-1/learning/<workspace>/`) so they persist across task worktrees.

## Configuration

`.bd-1.toml` is read live on every command, so edits take effect without re-registering. Besides the identity fields (`name`, `repo_path`, `default_branch`, `product_description`, `setup_script`), the knobs are:

| Knob | Default | Purpose |
|---|---|---|
| `max_attempts` | `5` | Execution/vet/review attempts before the run blocks. |
| `pi_command` | `"pi"` | Executor CLI. |
| `pi_model` | `""` | Optional model override passed to Pi. |
| `pi_provider` | `""` | Optional provider override passed to Pi. |
| `vet_command` | `"vet"` | Verifier CLI. |
| `vet_model` | `"flash"` | Model used by Vet. |
| `vet_confidence_threshold` | `0.8` | Passed to Vet as `--confidence-threshold`. |
| `dspy_model` | `"openai/gpt-5-mini"` | Model for DSPy reasoning programs. |
| `dspy_num_retries` | `3` | LM-level retries for transient DSPy/provider failures. |
| `discovery_max_iters` | `12` | Max tool-calling iterations for ReAct discovery. |
| `discovery_mcp_servers` | `[]` | Stdio MCP server commands providing external research tools for discovery (see "External research tools (MCP)"). |
| `dirty_exit_prompt` | `"commit and resolve before exit"` | Prompt used when Pi exits with uncommitted work. |
| `pr_command` | `"gh"` | GitHub CLI used for the PR lifecycle. |
| `pr_monitor_wait_seconds` | `600` | Delay before each PR monitor poll. Use `0` only for tests or controlled smoke runs. |
| `max_pr_monitor_polls` | `6` | Max monitor polls while waiting for checks/review. |
| `max_pr_feedback_attempts` | `3` | PR feedback rounds before the run blocks (separate from `max_attempts`). |
| `pr_base_branch` | `""` | PR base branch override (empty = repository default). |
| `pr_draft` | `false` | Create the PR as a draft. |
| `pr_comment_ignore_authors` | `[]` | PR comment authors to ignore when collecting actionable feedback. |

Raw run state and rebuildable caches stay out of normal commits:

```text
.sessions/
*.db
*.sqlite
```

Task worktrees also ignore runtime artifact subdirectories such as `.artifacts/context/`, `.artifacts/plans/`, `.artifacts/reviews/`, `.artifacts/completed/`, `.artifacts/blockers/`, `.artifacts/pr/`, and `.artifacts/learning/`.

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

## Intentional divergences from the original spec

Two owner-approved deviations and one CLI-shape difference are deliberate:

1. **Global learning store.** Learnings and DSPy examples live in `~/.bd-1/learning/<workspace>/`, not in-repo `.learning/` / `.examples/` as the original requirement says. They must survive task-worktree cleanup and never dirty task branches.
2. **Polling instead of webhooks.** Merge-triggered learning is `bd-1 sync` polling `gh pr view`, a deliberate stand-in for the original webhook design. Webhook support is backlog; run `bd-1 sync` on a schedule until it lands.
3. **Explicit `--repo`.** `bd-1 workspace add` takes the repository path explicitly via `--repo`, while the original spec assumes registering the current folder.
