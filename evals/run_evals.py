"""Live evaluation runner — drives the real Runtime against seed tasks in evals/tasks.py.

    uv run python -m evals.run_evals --list
    uv run python -m evals.run_evals --self-test        # offline, no tokens
    uv run python -m evals.run_evals --runs 3            # live, costs tokens
    uv run python -m evals.run_evals --task fix_failing_test --json evals/results.json
"""

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from carrot.client import OpenAICompatibleClient
from evals.tasks import TASKS
from harness import drive_agent
from harness.scripted_client import ScriptedClient


def _require_live_client() -> OpenAICompatibleClient:
    client = OpenAICompatibleClient()
    if not client.model or not client.api_key:
        raise SystemExit(
            "OPENAI_MODEL / OPENAI_API_KEY not set — copy .env.example to .env and fill "
            "them in (live evals call the real model and spend tokens)."
        )
    return client


def _run_once(client, task, run_index: int) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"carrot-eval-{task.id}-") as ws_dir:
        ws = Path(ws_dir)
        task.setup(ws)
        started = time.time()
        result = drive_agent(
            client, ws, task.prompt,
            settings_rules={
                ("bash_exec", "mutation"): True,
                ("write_file", "mutation"): True,
                ("edit_file", "mutation"): True,
            },
        )
        print()  # Runtime streams content without a trailing newline
        elapsed = time.time() - started
        passed, detail = task.check(ws, result.report, result.final_content)

    report = result.report or {}
    return {
        "task": task.id,
        "run": run_index,
        "passed": passed,
        "detail": detail,
        "tool_calls": report.get("tool_calls") or {},
        "prompt_tokens": report.get("prompt_tokens"),
        "total_prompt_tokens": report.get("total_prompt_tokens"),
        "completion_tokens": report.get("completion_tokens"),
        "billed_tokens": report.get("billed_tokens"),
        "duration_seconds": report.get("duration_seconds") or elapsed,
    }


def _billed(r: dict) -> int:
    # True API cost = sum of every turn's prompt (context is re-sent each turn)
    # plus all completions. Falls back to peak-context accounting for reports
    # written before total_prompt_tokens existed.
    prompt = r.get("total_prompt_tokens")
    if prompt is None:
        prompt = r.get("prompt_tokens") or 0
    return prompt + (r["completion_tokens"] or 0)


def _print_table(records: list[dict]) -> None:
    print(f"{'task':<22}{'run':<5}{'pass':<6}{'tools':<8}{'billed_tok':<12}{'dur(s)':<8}")
    for r in records:
        tools = sum(r["tool_calls"].values()) if r["tool_calls"] else 0
        print(
            f"{r['task']:<22}{r['run']:<5}{'yes' if r['passed'] else 'no':<6}"
            f"{tools:<8}{_billed(r):<12}{r['duration_seconds']:.1f}"
        )


def _print_summary(records: list[dict], task_ids: list[str]) -> None:
    print("\n--- summary ---")
    for task_id in task_ids:
        task_records = [r for r in records if r["task"] == task_id]
        if not task_records:
            continue
        pass_rate = sum(r["passed"] for r in task_records) / len(task_records)
        pass_at_k = any(r["passed"] for r in task_records)
        print(f"{task_id}: pass_rate={pass_rate:.0%} pass@{len(task_records)}={pass_at_k}")

    total_billed = sum(_billed(r) for r in records)
    avg_billed = total_billed / len(records) if records else 0
    overall = sum(r["passed"] for r in records) / len(records) if records else 0
    print(
        f"overall pass_rate={overall:.0%} "
        f"billed_tokens total={total_billed} avg_per_run={avg_billed:.0f}"
    )


def self_test() -> int:
    """Offline sanity check: a scripted model that actually fixes the bug in
    fix_failing_test, proving the harness wiring works without spending tokens.
    """
    task = next(t for t in TASKS if t.id == "fix_failing_test")
    with tempfile.TemporaryDirectory(prefix="carrot-eval-selftest-") as ws_dir:
        ws = Path(ws_dir)
        task.setup(ws)
        client = ScriptedClient([
            {"tool_calls": [{
                "name": "edit_file",
                "arguments": {
                    "file_path": str(ws / "calc.py"),
                    "old_string": "    return a + b  # bug",
                    "new_string": "    return a - b",
                },
            }]},
            {"content": "Fixed the bug: subtract was adding instead of subtracting."},
        ])
        result = drive_agent(
            client, ws, task.prompt,
            settings_rules={("edit_file", "mutation"): True},
        )
        passed, detail = task.check(ws, result.report, result.final_content)

    print(f"\nself-test: {'PASS' if passed else 'FAIL'}\n{detail}")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list available tasks and exit")
    parser.add_argument(
        "--self-test", action="store_true", help="offline harness sanity check, no tokens"
    )
    parser.add_argument("--task", help="only run this task id")
    parser.add_argument("--runs", type=int, default=1, help="repeat each task N times (pass@k)")
    parser.add_argument("--json", help="write results to this path")
    args = parser.parse_args()

    if args.list:
        for t in TASKS:
            print(f"{t.id}: {t.prompt}")
        return 0

    if args.self_test:
        return self_test()

    tasks = [t for t in TASKS if t.id == args.task] if args.task else TASKS
    if not tasks:
        raise SystemExit(f"no task matching --task {args.task!r}; use --list")

    client = _require_live_client()

    records = []
    for task in tasks:
        for run_index in range(args.runs):
            record = _run_once(client, task, run_index)
            records.append(record)
            print(f"[{task.id} #{run_index}] {'PASS' if record['passed'] else 'FAIL'}")

    print()
    _print_table(records)
    _print_summary(records, [t.id for t in tasks])

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"generated_at": time.time(), "records": records}, fh, indent=2)
        print(f"\nWrote {args.json}")

    return 0 if all(r["passed"] for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
