"""Shared driver for evals/ and audit/: run Carrot's real Runtime against a
throwaway workspace and get back its final answer, run report, and message
history — without touching the developer's real ~/.carrot or repo.
"""

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from carrot import permissions, workspace
from carrot.prompts import system_prompt_prefix
from carrot.runtime import Runtime
from carrot.workspace import WorkspaceContext


def build_workspace_context(workspace_dir) -> WorkspaceContext:
    """A non-git WorkspaceContext rooted at workspace_dir — no git subprocess calls."""
    workspace_dir = str(workspace_dir)
    return WorkspaceContext(cwd=workspace_dir, repo_root=workspace_dir, is_git_repo=False)


def seed_settings(workspace_dir, rules: dict[tuple[str, str], bool] | None) -> None:
    """Pre-seed .carrot/settings.json so drive_agent() goes through the real
    permission gate without hitting the blocking input() prompt. rules maps
    (tool_name, reason) -> allowed.
    """
    if not rules:
        return
    settings_path = Path(workspace_dir) / ".carrot" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = {
        permissions._rule_key(tool, reason): ("allow" if allowed else "deny")
        for (tool, reason), allowed in rules.items()
    }
    settings_path.write_text(json.dumps(encoded, indent=2))


@contextlib.contextmanager
def _isolated_home():
    """Redirect $HOME for the duration of a run, so Memory/session state lands
    in throwaway space instead of the real ~/.carrot.
    """
    old_home = os.environ.get("HOME")
    with tempfile.TemporaryDirectory(prefix="carrot-harness-home-") as tmp_home:
        os.environ["HOME"] = tmp_home
        try:
            yield
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


@dataclass
class AgentRun:
    final_content: str
    report: dict | None
    messages: list[dict]


def drive_agent(client, workspace_dir, prompt: str, settings_rules=None) -> AgentRun:
    """Run one Carrot turn end-to-end in an isolated workspace + isolated $HOME.

    Reuses the real Runtime.build/run and the run report Runtime already writes
    to <memory_dir>/runs/<run_id>.json — no metrics are re-derived here.
    """
    workspace_dir = str(Path(workspace_dir).resolve())
    seed_settings(workspace_dir, settings_rules)

    with _isolated_home():
        ctx = build_workspace_context(workspace_dir)
        workspace.set_current(ctx)
        rt = Runtime.build(client, ctx, system_prompt_prefix=system_prompt_prefix)
        content = rt.run(prompt)

        runs_dir = rt.event_log.path.parent / "runs"
        report_files = sorted(runs_dir.glob("*.json")) if runs_dir.exists() else []
        report = json.loads(report_files[-1].read_text()) if report_files else None

    return AgentRun(final_content=content, report=report, messages=list(rt.messages))
