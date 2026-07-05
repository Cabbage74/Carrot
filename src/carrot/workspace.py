from dataclasses import dataclass
import subprocess
import textwrap
from pathlib import Path

IMPORTANT_FILES = ["CARROT.md", "README.md", "pyproject.toml", "go.mod", "Cargo.toml", "package.json"]

def _clip(text: str, limit: int = 1500) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"

@dataclass
class WorkspaceContext:
    cwd: str
    repo_root: str
    is_git_repo: bool
    current_branch: str | None = None
    default_branch: str | None = None
    status: str | None = None
    recent_commits: list[str] | None = None
    important_files: dict[str, str] | None = None

    @classmethod
    def build(cls):
        cwd = Path.cwd().resolve()

        def git(args, fallback=""):
            try:
                result = subprocess.run(
                    ["git", *args], cwd=cwd,
                    capture_output=True, text=True,
                    check=True, timeout=5,
                )
                return result.stdout.strip() or fallback
            except Exception:
                return fallback
     
        is_git_repo = git(["rev-parse", "--is-inside-work-tree"]) == "true"
        if not is_git_repo:
            return cls(
                cwd=str(cwd),
                repo_root=str(cwd),
                is_git_repo=False,
                current_branch=None,
                default_branch=None,
                status=None,
                recent_commits=None,
                important_files=None,
            )
        
        repo_root = Path(git(["rev-parse", "--show-toplevel"], str(cwd))).resolve()
        
        files = {}
        for name in IMPORTANT_FILES:
            path = repo_root / name
            if not path.exists():
                continue
            key = str(path.relative_to(repo_root))
            files[key] = _clip(
                path.read_text(encoding="utf-8", errors="replace")
            )
        
        remotes = git(["remote"]).splitlines()
        remote = "origin" if "origin" in remotes else (remotes[0] if remotes else "origin")
        default_branch = git(
            ["symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD"], "unknown"
        ).removeprefix(f"{remote}/")

        return cls(
            cwd=str(cwd),
            repo_root=str(repo_root),
            is_git_repo=is_git_repo,
            current_branch=git(["branch", "--show-current"], "unknown"),
            default_branch=default_branch,
            status=_clip(git(["status", "--short"])) or "clean",
            recent_commits=[
                line for line in git(["log", "--oneline", "-5"]).splitlines() if line
            ],
            important_files=files
        )

    def text(self) -> str:
        lines = [
            "Workspace:",
            f"- cwd: {self.cwd}",
            f"- repo_root: {self.repo_root}",
        ]

        if not self.is_git_repo:
            return "\n".join(lines)

        lines.extend([
            f"- current_branch: {self.current_branch}",
            f"- default_branch: {self.default_branch}",
            "- status:",
        ])
        if self.status: 
            lines.append(textwrap.indent(self.status, "  ") or "  (clean)")

        lines.append("- recent_commits:")
        if self.recent_commits:
            for line in self.recent_commits:
                lines.append(f"  - {line}")
        else:
            lines.append("  - none")

        lines.append("- important_files:")
        if self.important_files:
            for path, snippet in self.important_files.items():
                lines.append(f"  - {path}")
                lines.append(textwrap.indent(snippet, "    "))
        else:
            lines.append("  - none")

        return "\n".join(lines)