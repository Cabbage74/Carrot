"""Seed task suite for evals/run_evals.py.

Each EvalTask is: a fixture setup (files written into a throwaway workspace),
a natural-language prompt handed to the live agent, and a deterministic
checker run afterward. Add tasks by appending to TASKS.
"""

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EvalTask:
    id: str
    prompt: str
    setup: Callable[[Path], None]
    check: Callable[[Path, dict | None, str], tuple[bool, str]]


def _run_pytest(workspace_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=workspace_dir, capture_output=True, text=True, timeout=60,
    )


# --- fix_failing_test ----------------------------------------------------

def _setup_fix_failing_test(ws: Path):
    (ws / "calc.py").write_text(
        "def add(a, b):\n"
        "    return a + b\n\n"
        "def subtract(a, b):\n"
        "    return a + b  # bug\n"
    )
    (ws / "test_calc.py").write_text(
        "from calc import add, subtract\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n\n"
        "def test_subtract():\n"
        "    assert subtract(5, 3) == 2\n"
    )


def _check_fix_failing_test(ws: Path, report, final_content: str) -> tuple[bool, str]:
    result = _run_pytest(ws)
    return result.returncode == 0, f"pytest exit={result.returncode}\n{result.stdout[-800:]}"


# --- implement_function ---------------------------------------------------

def _setup_implement_function(ws: Path):
    (ws / "slugify.py").write_text(
        "def slugify(text: str) -> str:\n"
        '    """Convert text to a URL-friendly slug: lowercase, collapse runs of\n'
        "    whitespace/underscores/punctuation into single hyphens, and strip\n"
        '    leading/trailing hyphens."""\n'
        "    raise NotImplementedError\n"
    )
    (ws / "test_slugify.py").write_text(
        "from slugify import slugify\n\n"
        "def test_basic():\n"
        '    assert slugify("Hello World") == "hello-world"\n\n'
        "def test_underscores():\n"
        '    assert slugify("foo_bar_baz") == "foo-bar-baz"\n\n'
        "def test_strips_punctuation():\n"
        '    assert slugify("Hello, World!!!") == "hello-world"\n\n'
        "def test_collapses_runs():\n"
        '    assert slugify("a   b--c") == "a-b-c"\n'
    )


def _check_implement_function(ws: Path, report, final_content: str) -> tuple[bool, str]:
    result = _run_pytest(ws)
    return result.returncode == 0, f"pytest exit={result.returncode}\n{result.stdout[-800:]}"


# --- answer_from_code ------------------------------------------------------

def _setup_answer_from_code(ws: Path):
    (ws / "config.py").write_text(
        "HOST = \"0.0.0.0\"\n"
        "DEFAULT_PORT = 8421\n"
        "MAX_RETRIES = 3\n"
    )


def _check_answer_from_code(ws: Path, report, final_content: str) -> tuple[bool, str]:
    passed = "8421" in final_content
    return passed, f"final_content={final_content!r}"


# --- multi_file_rename ------------------------------------------------------

def _setup_multi_file_rename(ws: Path):
    (ws / "service.py").write_text(
        "def old_name(x):\n"
        "    return x * 2\n"
    )
    (ws / "main.py").write_text(
        "from service import old_name\n\n"
        "if __name__ == \"__main__\":\n"
        "    print(old_name(21))\n"
    )


def _check_multi_file_rename(ws: Path, report, final_content: str) -> tuple[bool, str]:
    service = (ws / "service.py").read_text()
    main = (ws / "main.py").read_text()
    no_old = "old_name" not in service and "old_name" not in main
    has_new = "new_name" in service and "new_name" in main
    if not (no_old and has_new):
        detail = f"old_name present or new_name missing.\nservice.py:\n{service}\nmain.py:\n{main}"
        return False, detail

    result = subprocess.run(
        [sys.executable, "-c", "import service; assert hasattr(service, 'new_name')"],
        cwd=ws, capture_output=True, text=True, timeout=30,
    )
    detail = f"import check exit={result.returncode} stderr={result.stderr[-400:]}"
    return result.returncode == 0, detail


TASKS: list[EvalTask] = [
    EvalTask(
        id="fix_failing_test",
        prompt="There's a failing test in this project. Find and fix the bug so all tests pass.",
        setup=_setup_fix_failing_test,
        check=_check_fix_failing_test,
    ),
    EvalTask(
        id="implement_function",
        prompt="Implement the slugify function in slugify.py so the tests in test_slugify.py pass.",
        setup=_setup_implement_function,
        check=_check_implement_function,
    ),
    EvalTask(
        id="answer_from_code",
        prompt="What is the value of DEFAULT_PORT in config.py? Answer with just the number.",
        setup=_setup_answer_from_code,
        check=_check_answer_from_code,
    ),
    EvalTask(
        id="multi_file_rename",
        prompt="Rename the function old_name to new_name everywhere in this project, "
               "keeping its behavior unchanged.",
        setup=_setup_multi_file_rename,
        check=_check_multi_file_rename,
    ),
]
