from carrot import permissions


def test_classify_exempts_read_within_workspace(tmp_path):
    args = {"file_path": str(tmp_path / "a.txt")}
    reason = permissions.classify("read_file", args, str(tmp_path))
    assert reason is None


def test_classify_flags_read_escaping_workspace(tmp_path, monkeypatch):
    outside = tmp_path.parent / "outside.txt"
    reason = permissions.classify("read_file", {"file_path": str(outside)}, str(tmp_path))
    assert reason == "path_escape"


def test_classify_flags_write_inside_workspace_as_mutation(tmp_path):
    args = {"file_path": str(tmp_path / "a.txt")}
    reason = permissions.classify("write_file", args, str(tmp_path))
    assert reason == "mutation"


def test_classify_prefers_path_escape_over_mutation(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    reason = permissions.classify("write_file", {"file_path": str(outside)}, str(tmp_path))
    assert reason == "path_escape"


def test_classify_flags_bash_exec_as_mutation(tmp_path):
    reason = permissions.classify("bash_exec", {"command": "ls"}, str(tmp_path))
    assert reason == "mutation"


def test_is_within_workspace_handles_dotdot_traversal(tmp_path):
    (tmp_path / "sub").mkdir()
    escaping = str(tmp_path / "sub" / ".." / ".." / "outside.txt")
    assert not permissions.is_within_workspace(escaping, str(tmp_path))


def test_lookup_rule_defaults_to_none(tmp_path):
    assert permissions.lookup_rule("bash_exec", "mutation", str(tmp_path)) is None


def test_save_and_lookup_rule_round_trip(tmp_path):
    permissions._save_rule(str(tmp_path), "bash_exec", "mutation", True)
    assert permissions.lookup_rule("bash_exec", "mutation", str(tmp_path)) is True

    permissions._save_rule(str(tmp_path), "write_file", "mutation", False)
    assert permissions.lookup_rule("write_file", "mutation", str(tmp_path)) is False
    # first rule still there — rules accumulate rather than overwrite the file
    assert permissions.lookup_rule("bash_exec", "mutation", str(tmp_path)) is True


def test_ask_user_always_allow_persists_rule(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "a")
    allowed = permissions.ask_user("bash_exec", {"command": "ls"}, "mutation", str(tmp_path))
    assert allowed is True
    assert permissions.lookup_rule("bash_exec", "mutation", str(tmp_path)) is True


def test_ask_user_deny_always_persists_rule(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "d")
    allowed = permissions.ask_user("bash_exec", {"command": "ls"}, "mutation", str(tmp_path))
    assert allowed is False
    assert permissions.lookup_rule("bash_exec", "mutation", str(tmp_path)) is False


def test_ask_user_reprompts_on_invalid_answer(tmp_path, monkeypatch, capsys):
    answers = iter(["nonsense", "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    allowed = permissions.ask_user("bash_exec", {"command": "ls"}, "mutation", str(tmp_path))
    assert allowed is True
    assert permissions.lookup_rule("bash_exec", "mutation", str(tmp_path)) is None
