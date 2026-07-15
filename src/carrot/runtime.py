import json
import time
import uuid
from pathlib import Path

from . import permissions, sandbox, tui, workspace
from .checkpoint import EventLog, SessionMeta, build_report, replay
from .client import OpenAICompatibleClient
from .context_governor import ContextGovernor
from .log import logger
from .memory import Memory
from .memory import current as current_memory
from .memory import set_current as set_current_memory
from .message import StreamingToolCallAccumulator
from .tools import toolbox
from .tools.bash_exec import run_bash
from .workspace import WorkspaceContext

REMINDER_THRESHOLD = 5
REMINDER_TEXT = (
    "Reminder: you've made several tool calls without touching update_task_summary "
    "or write_episodic_note. If anything so far is worth carrying forward, record it now."
)
INTERRUPTED_TOOL_RESULT = (
    "Error: interrupted before this call's result was recorded — it may or may not have "
    "already executed. This tool can have side effects; verify its actual effect first "
    "(e.g. check the file or command output) before deciding whether to redo it."
)
DENIED_ON_RESUME_RESULT = (
    "Error: denied. This call required user approval before executing, but the session "
    "was interrupted while waiting for a response, so it was never run. Request it again "
    "if it's still needed."
)

class Runtime:
    def __init__(self, client, workspace_context, system_prompt_prefix, messages,
                 session_id, event_log, meta, meta_path):
        self.client = client
        self.workspace_context = workspace_context
        self.system_prompt_prefix = system_prompt_prefix
        self.messages = messages
        self.session_id = session_id
        self.event_log = event_log
        self.meta = meta
        self.meta_path = meta_path
        self.context_governor = ContextGovernor(client)
        self.usage = None
        self.pending_confirmation_ids: set[str] = set()

    @classmethod
    def build(
        cls,
        client: OpenAICompatibleClient,
        workspace_context: WorkspaceContext,
        system_prompt_prefix: str,
    ):
        session_id = uuid.uuid4().hex[:12]
        workspace.set_current(workspace_context)

        system_prompt = system_prompt_prefix + "\n\n"
        system_prompt += workspace_context.text()
        logger.debug("System prompt:\n%s", system_prompt)

        mem = Memory.build(Path(workspace_context.repo_root), session_id=session_id)
        set_current_memory(mem)
        memory_snapshot = current_memory().render()
        logger.debug("Memory snapshot:\n%s", memory_snapshot)

        meta_path = mem.memory_dir / "meta.json"
        meta = SessionMeta.load_or_create(meta_path, session_id, str(workspace_context.repo_root))

        return cls(
            client=client,
            workspace_context=workspace_context,
            system_prompt_prefix=system_prompt_prefix,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": memory_snapshot}
            ],
            session_id=session_id,
            event_log=EventLog(mem.memory_dir / "events.jsonl"),
            meta=meta,
            meta_path=meta_path,
        )

    @classmethod
    def resume(cls, client, workspace_context, system_prompt_prefix, session_id):
        workspace.set_current(workspace_context)
        system_prompt = system_prompt_prefix + "\n\n" + workspace_context.text()

        mem = Memory.build(Path(workspace_context.repo_root), session_id=session_id)
        set_current_memory(mem)

        meta_path = mem.memory_dir / "meta.json"
        meta = SessionMeta.load_or_create(meta_path, session_id, str(workspace_context.repo_root))
        events_path = mem.memory_dir / "events.jsonl"
        messages, pending_run_id, pending_confirmation_ids = replay(events_path)
        # replay() returns messages[0]/[1] as empty placeholders (so context_mutation
        # events, whose indices were recorded against the live 2-header layout, apply
        # cleanly) — fill them with the real system prompt / memory snapshot now.
        messages[0] = {"role": "system", "content": system_prompt}
        messages[1] = {"role": "system", "content": current_memory().render()}

        runtime = cls(
            client=client,
            workspace_context=workspace_context,
            system_prompt_prefix=system_prompt_prefix,
            messages=messages,
            session_id=session_id,
            event_log=EventLog(events_path),
            meta=meta,
            meta_path=meta_path,
        )
        runtime.pending_confirmation_ids = pending_confirmation_ids

        if pending_run_id:
            runtime.continue_run(pending_run_id)

        return runtime

    def run(self, user_input: str) -> str:
        run_id = uuid.uuid4().hex[:8]

        self.meta.status = "in_run"
        self.meta.first_input = self.meta.first_input or user_input
        self.meta.save(self.meta_path)

        self.messages.append({"role": "user", "content": user_input})
        self.event_log.append("run_start", run_id, user_input=user_input)

        logger.debug("User ask:\n%s", user_input)

        return self._loop(run_id)

    def continue_run(self, run_id: str) -> str:
        last = self.messages[-1]

        if last["role"] == "assistant" and not last.get("tool_calls"):
            # crashed after the model's final reply but before the run_end
            # bookkeeping below got written — the run is already done, don't ask
            # the model to answer again.
            return self._finish_run(run_id, last["content"] or "")

        if last["role"] == "assistant" and last.get("tool_calls"):
            done_ids = {m["tool_call_id"] for m in self.messages if m["role"] == "tool"}
            for tc in last["tool_calls"]:
                if tc["id"] in done_ids:
                    continue
                if tc["id"] in self.pending_confirmation_ids:
                    # it never executed — we were still blocked on the user's answer
                    # when the crash happened, so "denied" is a fact, not a guess.
                    content = DENIED_ON_RESUME_RESULT
                else:
                    # don't blindly re-run it — we can't tell if it already executed
                    # before the crash, so let the model decide, after checking for itself.
                    content = INTERRUPTED_TOOL_RESULT
                self.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": content})
                self.event_log.append("tool_result", run_id, tool_call_id=tc["id"],
                                       tool_name=tc["function"]["name"], content=content)

        return self._loop(run_id)

    def _finish_run(self, run_id: str, content: str) -> str:
        self.event_log.append("run_end", run_id, content=content)
        self.meta.status = "idle"
        self.meta.last_active_at = time.time()
        self.meta.save(self.meta_path)

        report = build_report(self.event_log.path, run_id)
        reports_dir = self.event_log.path.parent / "runs"
        reports_dir.mkdir(exist_ok=True)
        (reports_dir / f"{run_id}.json").write_text(json.dumps(report, indent=2))

        return content

    def _require_approval(self, tc, reason: str, run_id: str) -> bool:
        workspace_root = self.workspace_context.repo_root
        rule = permissions.lookup_rule(tc.name, reason, workspace_root)
        if rule is not None:
            return rule
        # log before the blocking prompt so a crash mid-prompt is provably
        # "never executed", not merely "unknown" — see continue_run().
        self.event_log.append("awaiting_confirmation", run_id, tool_call_id=tc.id,
                               tool_name=tc.name, reason=reason)
        return permissions.ask_user(tc.name, tc.arguments, reason, workspace_root)

    def _execute_tool_call(self, tc, run_id: str) -> str:
        workspace_root = self.workspace_context.repo_root

        reason = permissions.classify(tc.name, tc.arguments, workspace_root)
        if reason is not None and not self._require_approval(tc, reason, run_id):
            return f"Error: denied by user — {tc.name} requires approval ({reason})."

        result = toolbox.execute(tc.name, tc.arguments)

        if tc.name == "bash_exec" and sandbox.looks_like_network_failure(result):
            if self._require_approval(tc, "network_escape", run_id):
                result = run_bash(tc.arguments["command"], tc.arguments.get("timeout", 120),
                                   allow_network=True)

        return result

    def _loop(self, run_id: str) -> str:
        while True:
            mutation = self.context_governor.govern(self.messages, self.usage)
            if mutation:
                self.event_log.append("context_mutation", run_id, mutation=mutation)

            mem = current_memory()

            memory_snapshot = mem.render()
            logger.debug("Memory snapshot:\n%s", memory_snapshot)
            self.messages[1]["content"] = memory_snapshot

            if mem.tool_calls_since_update >= REMINDER_THRESHOLD:
                self.messages.append({"role": "system", "content": REMINDER_TEXT})
                # Log it: this appends a message to self.messages, so any later
                # context_mutation records indices against a list that includes
                # it. replay() must reconstruct it too or those indices misalign.
                self.event_log.append("reminder", run_id, content=REMINDER_TEXT)
                mem.tool_calls_since_update = 0

            content = ""
            tool_call_accums: dict[int, StreamingToolCallAccumulator] = {}
            with tui.assistant_stream() as stream:
                for chunk in self.client.respond_stream(
                    self.messages, tools=toolbox.get_openai_schema()
                ):
                    if chunk.usage:
                        self.usage = chunk.usage
                        logger.debug("Turn usage: %s", self.usage)
                        continue

                    delta = chunk.choices[0].delta

                    if delta.content:
                        stream.feed(delta.content)
                        content += delta.content

                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_call_accums:
                                tool_call_accums[idx] = StreamingToolCallAccumulator(index=idx)
                            acc = tool_call_accums[idx]
                            if tc_delta.id:
                                acc.id = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    acc.name = tc_delta.function.name
                                if tc_delta.function.arguments:
                                    acc.arguments += tc_delta.function.arguments

            tool_calls = [tc for a in tool_call_accums.values() if (tc := a.finalize())]

            assistant_message = {"role": "assistant", "content": content or None}
            if tool_calls:
                assistant_message["tool_calls"] = [tc.to_openai_format() for tc in tool_calls]
            self.messages.append(assistant_message)
            self.event_log.append(
                "assistant_message", run_id, message=assistant_message,
                usage=self.usage.model_dump() if self.usage else None,
            )

            if not tool_calls:
                return self._finish_run(run_id, content)

            for tc in tool_calls:
                tui.tool_activity(tc.name)
                result = self._execute_tool_call(tc, run_id)
                logger.debug("Tool %s Executed with args: %s", tc.name, json.dumps(tc.arguments))

                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                self.event_log.append("tool_result", run_id, tool_call_id=tc.id,
                                      tool_name=tc.name, content=result)
                logger.debug("Tool %s Result:\n%s", tc.name, result)

                if tc.name in ("update_task_summary", "write_episodic_note"):
                    mem.tool_calls_since_update = 0
                else:
                    mem.tool_calls_since_update += 1
