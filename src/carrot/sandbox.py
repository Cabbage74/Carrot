import shutil
import subprocess

NETWORK_ERROR_MARKERS = (
    "could not resolve host",
    "connection refused",
    "network is unreachable",
    "temporary failure in name resolution",
    "connection timed out",
    "could not connect",
    "unable to connect",
)


def bubblewrap_available() -> bool:
    return shutil.which("bwrap") is not None


def looks_like_network_failure(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in NETWORK_ERROR_MARKERS)


def build_bwrap_argv(command: str, workspace_root: str, allow_network: bool) -> list[str]:
    # bwrap applies --*bind/--tmpfs in argv order, and later ones shadow earlier
    # ones at overlapping paths — the workspace bind must come last so it wins
    # even when workspace_root happens to live under /tmp.
    argv = [
        "bwrap",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--bind", workspace_root, workspace_root,
        "--die-with-parent",
        "--chdir", workspace_root,
    ]
    if not allow_network:
        argv.append("--unshare-net")
    argv += ["sh", "-c", command]
    return argv


def run_sandboxed(
    command: str, workspace_root: str, timeout: int, allow_network: bool
) -> subprocess.CompletedProcess:
    if not bubblewrap_available():
        raise RuntimeError(
            "bubblewrap (bwrap) is not installed — sandboxed execution is unavailable. "
            "Install it with e.g. `sudo apt-get install bubblewrap` on Debian/Ubuntu."
        )
    argv = build_bwrap_argv(command, workspace_root, allow_network)
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
