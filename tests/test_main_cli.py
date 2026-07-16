import pytest

from carrot import main, sandbox


@pytest.fixture(autouse=True)
def _reset_sandbox_state():
    original = sandbox.enabled()
    yield
    sandbox.set_enabled(original)


def test_parse_args_default_is_unsafe():
    assert main.parse_args([]).safe is False


def test_parse_args_single_dash_safe():
    assert main.parse_args(["-safe"]).safe is True


def test_parse_args_double_dash_safe():
    assert main.parse_args(["--safe"]).safe is True


def test_configure_sandbox_default_disables(monkeypatch):
    monkeypatch.setattr(sandbox, "bubblewrap_available", lambda: True)
    main.configure_sandbox(False)
    assert sandbox.enabled() is False


def test_configure_sandbox_safe_enables_when_available(monkeypatch):
    monkeypatch.setattr(sandbox, "bubblewrap_available", lambda: True)
    main.configure_sandbox(True)
    assert sandbox.enabled() is True


def test_configure_sandbox_safe_warns_and_exits_when_unavailable(monkeypatch):
    monkeypatch.setattr(sandbox, "bubblewrap_available", lambda: False)
    warnings = []
    monkeypatch.setattr(main.tui, "warn", lambda msg: warnings.append(msg))
    with pytest.raises(SystemExit) as exc:
        main.configure_sandbox(True)
    assert exc.value.code == 1
    assert warnings and "bubblewrap" in warnings[0]
    assert sandbox.enabled() is False
