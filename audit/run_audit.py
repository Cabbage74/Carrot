"""Standalone audit report runner.

    uv run python -m audit.run_audit [--json audit/results.json]

Runs every scenario in audit.scenarios.SCENARIOS, groups findings by category,
and prints a report. Exits nonzero only when an attack that was expected to be
blocked actually succeeded (or a positive control unexpectedly failed) —
documented "known_gap" scenarios never fail the run.
"""

import argparse
import json
import sys
import time
from collections import defaultdict

from audit.scenarios import SCENARIOS, evaluate
from carrot import sandbox


def run(scenarios) -> list[dict]:
    bwrap_ok = sandbox.bubblewrap_available()
    findings = []
    for scenario in scenarios:
        if scenario.requires_bwrap and not bwrap_ok:
            findings.append({
                "id": scenario.id, "category": scenario.category,
                "description": scenario.description, "expected": scenario.expected,
                "outcome": "skipped", "label": "SKIPPED (bwrap unavailable)",
                "detail": "bubblewrap is not installed", "ok": True,
            })
            continue
        finding = evaluate(scenario)
        findings.append({
            "id": finding.scenario.id, "category": finding.scenario.category,
            "description": finding.scenario.description, "expected": finding.scenario.expected,
            "outcome": finding.outcome, "label": finding.label,
            "detail": finding.detail, "ok": finding.ok,
        })
    return findings


def print_report(findings: list[dict]) -> None:
    by_category = defaultdict(list)
    for f in findings:
        by_category[f["category"]].append(f)

    for category in sorted(by_category):
        print(f"\n=== {category} ===")
        for f in by_category[category]:
            marker = "OK" if f["ok"] else "!!"
            print(f"[{marker}] {f['label']:<28} {f['id']}")
            print(f"       {f['description']}")
            print(f"       {f['detail']}")

    total = len(findings)
    unexpected = [f for f in findings if not f["ok"]]
    gaps = [f for f in findings if f["label"] == "KNOWN GAP"]
    skipped = [f for f in findings if f["outcome"] == "skipped"]
    print(
        f"\n{total} scenarios — {len(unexpected)} unexpected, "
        f"{len(gaps)} known gaps, {len(skipped)} skipped"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="write the findings report to this path")
    args = parser.parse_args()

    findings = run(SCENARIOS)
    print_report(findings)

    if args.json:
        report = {"generated_at": time.time(), "findings": findings}
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"\nWrote {args.json}")

    return 1 if any(not f["ok"] for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
