# Carrot Evals

Measures how reliably Carrot actually completes coding tasks — not just that
the code compiles. Each task in `evals/tasks.py` is a fixture (files written
into a throwaway workspace) + a natural-language prompt + a deterministic
checker (usually "does pytest pass in the workspace afterward").

## Running it

```bash
uv run python -m evals.run_evals --list          # see the task set
uv run python -m evals.run_evals --self-test      # offline, proves the harness works, no tokens
uv run python -m evals.run_evals --runs 3         # live: calls the model in .env, spends tokens
uv run python -m evals.run_evals --task fix_failing_test --json evals/results.json
```

Live runs need `OPENAI_API_KEY` / `OPENAI_MODEL` set (see `.env.example`).
This is intentionally **not** part of `make test` / CI — it costs tokens and
is non-deterministic across model versions.

## Methodology

- Every run gets a fresh temp workspace and a fresh Carrot session (isolated
  `$HOME`), driven through the real `Runtime.build`/`run` — the same code path
  the CLI uses, not a mock.
- Metrics (tokens, tool-call counts, duration, outcome) come straight from the
  run report `Runtime` already writes to `<memory_dir>/runs/<run_id>.json`
  (`carrot.checkpoint.build_report`) — the harness doesn't re-derive them.
- The reported `billed_tok` is the *true* API cost: every turn re-sends the
  whole growing context, so it sums each turn's prompt tokens (not just the
  final turn's) plus all completion tokens. The report also keeps
  `prompt_tokens` separately as the single-turn context peak.
- `--runs N` repeats a task N times to compute pass@N alongside the raw pass
  rate, since a single run can pass or fail by luck.
- Mutating tools (`bash_exec`, `write_file`, `edit_file`) are pre-approved for
  the ephemeral workspace only (via a seeded `.carrot/settings.json`) so a run
  never blocks on the interactive confirmation prompt.

## Extending

Add an `EvalTask` to `evals/tasks.py`: a `setup(workspace_dir)` that writes
fixture files, a `prompt`, and a `check(workspace_dir, report, final_content)`
returning `(passed, detail)`. Keep checkers deterministic (exit codes, file
contents, substring checks) rather than another LLM call, so results are
reproducible.
