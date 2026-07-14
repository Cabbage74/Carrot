import json
from pathlib import Path

# Tools with side effects — every call needs a "mutation" approval unless a
# .carrot rule already covers it.
MUTATING_TOOLS = {"bash_exec", "write_file", "edit_file"}

# Tools whose first argument is a filesystem path that could point outside
# the workspace.
PATH_ARG_TOOLS = {"read_file", "write_file", "edit_file"}


def is_within_workspace(file_path: str, workspace_root: str) -> bool:
    try:
        resolved = Path(file_path).resolve()
        root = Path(workspace_root).resolve()
    except OSError:
        return False
    return resolved == root or root in resolved.parents


def classify(tool_name: str, arguments: dict, workspace_root: str) -> str | None:
    """Return the approval reason this call needs, or None if it's exempt."""
    if tool_name in PATH_ARG_TOOLS:
        file_path = arguments.get("file_path")
        if file_path and not is_within_workspace(file_path, workspace_root):
            return "path_escape"
    if tool_name in MUTATING_TOOLS:
        return "mutation"
    return None


def _settings_path(workspace_root: str) -> Path:
    return Path(workspace_root) / ".carrot" / "settings.json"


def _rule_key(tool_name: str, reason: str) -> str:
    return f"{tool_name}:{reason}"


def _load_rules(workspace_root: str) -> dict:
    path = _settings_path(workspace_root)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_rule(workspace_root: str, tool_name: str, reason: str, allowed: bool) -> None:
    path = _settings_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rules = _load_rules(workspace_root)
    rules[_rule_key(tool_name, reason)] = "allow" if allowed else "deny"
    path.write_text(json.dumps(rules, indent=2, ensure_ascii=False) + "\n")


def lookup_rule(tool_name: str, reason: str, workspace_root: str) -> bool | None:
    """Return a remembered decision for this (tool, reason), or None if unset."""
    value = _load_rules(workspace_root).get(_rule_key(tool_name, reason))
    if value == "allow":
        return True
    if value == "deny":
        return False
    return None


def describe_request(tool_name: str, arguments: dict, reason: str) -> str:
    if reason == "path_escape":
        path = arguments.get("file_path")
        return f"{tool_name} wants to access a path outside the workspace: {path}"
    if reason == "network_escape":
        command = arguments.get("command")
        return f"bash_exec failed inside the network-isolated sandbox, may need network: {command}"
    return f"{tool_name} is a side-effecting call. Arguments: {arguments}"


def ask_user(tool_name: str, arguments: dict, reason: str, workspace_root: str) -> bool:
    print(f"\n[permission] {describe_request(tool_name, arguments, reason)}")
    while True:
        answer = input("Allow? [y]es / [n]o / [a]lways allow / [d]eny always: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no", ""):
            return False
        if answer in ("a", "always"):
            _save_rule(workspace_root, tool_name, reason, True)
            return True
        if answer in ("d", "deny", "deny always"):
            _save_rule(workspace_root, tool_name, reason, False)
            return False
        print("Please answer y / n / a / d")
