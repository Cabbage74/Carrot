# Carrot

Carrot is a coding agent.

## Install

```bash
uv tool install --editable .   # installs the `carrot` command, usable from any directory

mkdir -p ~/.carrot
cp .env.example ~/.carrot/.env
# edit ~/.carrot/.env — use your own api-key
```

`~/.carrot/.env` is the global default config. Drop a `.env` in a specific
project's directory to override it there (e.g. a different model per
project) — a local `.env` always wins over the global one.

## Run it

```bash
carrot          # default: bash runs unsandboxed
carrot -safe    # opt-in: run bash inside a bwrap sandbox (Linux + bubblewrap)
```

For local development inside this repo, `uv run python -m carrot` also works
without installing anything.

### Sandboxing (`-safe`)

By default `bash_exec` runs commands directly. Every side-effecting call still
needs approval and file access is still confined to the workspace — those checks
are OS-independent and always on.

Passing `-safe` additionally runs `bash_exec` inside a
[bubblewrap](https://github.com/containers/bubblewrap) sandbox: the workspace is
read-write, the rest of the host is read-only, and the network is cut unless a
command is approved for it. This requires `bwrap` on the `PATH` (Linux only). If
`-safe` is requested where bubblewrap isn't available, Carrot prints a warning
and exits so you can install it or drop the flag.

## Evaluation & audit

Two verification pillars live alongside the unit tests, each with its own
methodology writeup:

- [`evals/`](evals/README.md) — live task-success benchmarking (does the
  agent actually fix bugs / implement functions / answer questions about the
  code?). `make eval-selftest` for a free offline sanity check, `make eval`
  for a live run against your configured model.
- [`audit/`](audit/README.md) — adversarial verification of the permission
  gate and bwrap sandbox (path escapes, symlink escapes, sandbox writes,
  network isolation, a hijacked-model defense-in-depth check). `make audit`
  for a findings report, or `make test` runs the same scenarios as pytest.