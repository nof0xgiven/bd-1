# bd-1 roadmap / TODO

Status: the pipeline is feature-complete and proven end-to-end (task → discovery →
plan → execute → vet → review → PR → merge → learning → sync), with 302 passing
tests. What remains is hardening it from "works" to "reliable" and unlocking the
DSPy optimization loop. Ordered by priority.

## Tier 1 — Table stakes (next session)

- [ ] **LICENSE** — choose MIT or Apache-2.0 and add it; the repo is public and
      unusable downstream without one.
- [ ] **CI** — GitHub Actions workflow: `uv sync` + `uv run pytest -q` +
      `uv run ruff check` + `uv run ruff format --check` on push/PR. Add badge
      to README.
- [ ] **`bd-1 feedback` on cleaned runs** — currently collects evidence from the
      removed worktree (silently empty); root at the run archive like
      `bd-1 sync` already does (see `sync._learn_from_merge` for the pattern).
- [ ] **Learning ID overwrite guard** — LM-supplied learning ids can silently
      replace unrelated prior rules in the store; guard `save_learning` against
      overwriting a record whose `rule` text differs (suffix or reject).
- [ ] **Conflict rounds leave the completion summary stale** — the merge-conflict
      contract never updates the summary, so the post-merge review reads a
      narrative that omits the merge; add a summary-update line to
      `compile_conflict_resolution_prompt` consistent with the Revision Contract.
- [ ] **MCP tool-call timeout** — server *startup* is bounded (20s) but a tool
      call hanging mid-ReAct is not; wrap converted MCP tool invocations with a
      per-call timeout.

## Tier 2 — Reliability is an empirical claim

- [ ] **`bd-1 runs` / `bd-1 stats`** — list runs and aggregate the archive into
      numbers: first-attempt pass rate, attempts per task, block reasons,
      per-stage durations (transitions.jsonl already has timestamps), runs per
      workspace. Reliability needs a denominator.
- [ ] **Burn-in batch** — run 10–20 real tasks across 2–3 workspaces; record
      pass rate and where blocks cluster; fix what breaks. This also
      manufactures the optimization dataset (every archived run is a labeled
      example).
- [ ] **Learning curation CLI** — `bd-1 learnings list|show|promote|reject <id>`
      against the global store. Auto-saved learnings are injected into every
      future discovery; without curation the flywheel can spin backwards.
      Wire `usage_count`/`success_count` (in the schema, currently never
      updated) so curation has evidence.
- [ ] **`bd-1 resume <run-id>`** — BLOCKED is terminal today; resuming should
      reuse the existing discovery package and plan instead of re-paying for
      them.
- [ ] **Scheduler for `bd-1 sync`** — document/cron the polling loop (until
      webhooks exist) so merge learnings land without manual runs.

## Tier 3 — The DSPy payoff: optimization

- [ ] **Metrics** — define 2–3 programmatic metrics from run archives:
      review-passed-first-attempt, vet exit 0, PR merged without feedback
      rounds; learning-quality proxy from curation verdicts.
- [ ] **Eval set builder** — assemble dspy.Example sets from archived runs
      (`~/.bd-1/runs/`) and the per-workspace example stores.
- [ ] **Compile** — GEPA/MIPROv2 over the discovery and review programs once
      ~15–20 archived runs exist; persist with `program.save()` per workspace
      under the global state dir.
- [ ] **Load compiled programs** — `_build_reasoning` prefers a saved compiled
      program when one exists for the workspace; `bd-1 doctor` reports which
      programs are compiled vs seed.

## Backlog / later

- [ ] Webhook-triggered learning (replaces `bd-1 sync` polling; needs a server).
- [ ] Doctor: optional LM smoke test (one tiny completion) behind a flag.
- [ ] Per-attempt artifacts in the archive (currently final attempt only).
- [ ] `workspace add` from the current directory (original-spec ergonomics).
- [ ] ReAct tools for profiling (currently single-shot over collected evidence).
