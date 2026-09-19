"""Git integration layer to inspect changed files, branches, and merge bases."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitContext:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or self._find_git_root()

    @staticmethod
    def _find_git_root() -> Path:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            return Path(res.stdout.strip()).resolve()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return Path(".").resolve()

    def is_git_repo(self) -> bool:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.root,
                capture_output=True,
                text=True,
            )
            return res.returncode == 0 and res.stdout.strip() == "true"
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def get_current_branch(self) -> str | None:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
            )
            return res.stdout.strip() or None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def get_head_sha(self) -> str | None:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
            )
            return res.stdout.strip() or None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def get_changed_files(self, base_ref: str | None = None) -> list[str]:
        """Return list of changed files relative to base_ref (or unstaged/staged if none)."""
        if not self.is_git_repo():
            return []

        changed: set[str] = set()
        try:
            if base_ref:
                # Compare against base_ref
                res = subprocess.run(
                    ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0:
                    changed.update(line.strip() for line in res.stdout.splitlines() if line.strip())
                else:
                    # Fallback to direct diff
                    res = subprocess.run(
                        ["git", "diff", "--name-only", base_ref],
                        cwd=self.root,
                        capture_output=True,
                        text=True,
                    )
                    if res.returncode == 0:
                        changed.update(
                            line.strip() for line in res.stdout.splitlines() if line.strip()
                        )
            else:
                # Check staged and unstaged changes against HEAD
                res_unstaged = subprocess.run(
                    ["git", "diff", "--name-only"],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                )
                if res_unstaged.returncode == 0:
                    changed.update(
                        line.strip() for line in res_unstaged.stdout.splitlines() if line.strip()
                    )

                res_staged = subprocess.run(
                    ["git", "diff", "--name-only", "--cached"],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                )
                if res_staged.returncode == 0:
                    changed.update(
                        line.strip() for line in res_staged.stdout.splitlines() if line.strip()
                    )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        return sorted(list(changed))
