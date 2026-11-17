"""
Updating ModeSwitch from GitHub.

ModeSwitch is installed by cloning the repo, so an update is a `git pull`. The app
checks in the background for new commits on the branch it was installed from, and
offers them in the tray menu; applying one pulls, installs any new requirements,
and restarts.

Only a clean fast-forward is ever applied. A copy with local edits, or with commits
of its own (a developer's copy), is told why it cannot update instead.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROJECT = Path(__file__).resolve().parent.parent
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Never let a background check stop to ask for a password
_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    behind: int                     # new commits waiting
    changes: list[str] = field(default_factory=list)   # their subject lines, newest first
    blocked: str = ""               # why it cannot be applied, or "" if it can


def available() -> bool:
    """True when this copy was installed with git and can update itself."""
    return not getattr(sys, "frozen", False) and (PROJECT / ".git").exists()


def _git(*args: str, timeout: int = 60) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=PROJECT, capture_output=True, text=True,
                                timeout=timeout, env=_ENV, creationflags=_NO_WINDOW)
    except FileNotFoundError:
        raise UpdateError("Git is not installed, or not on the PATH")
    except subprocess.TimeoutExpired:
        raise UpdateError("GitHub did not answer in time")
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip().splitlines()
        raise UpdateError(message[-1] if message else f"git {args[0]} failed")
    return result.stdout.strip()


def check() -> Optional[UpdateInfo]:
    """Fetch and compare with the branch this copy follows. None if up to date."""
    _git("fetch", "--quiet", "origin")
    try:
        _git("rev-parse", "--abbrev-ref", "@{u}")
    except UpdateError:
        return None   # a local branch with nothing upstream to update from
    behind = int(_git("rev-list", "--count", "HEAD..@{u}") or 0)
    if not behind:
        return None
    changes = _git("log", "--format=%s", "HEAD..@{u}").splitlines()
    blocked = ""
    if int(_git("rev-list", "--count", "@{u}..HEAD") or 0):
        blocked = "This copy has commits of its own, so it is not updated automatically"
    elif _git("status", "--porcelain", "--untracked-files=no"):
        blocked = "This copy has local changes to its files, so it is not updated automatically"
    return UpdateInfo(behind, changes, blocked)


def apply() -> None:
    """Pull the new commits and install any new requirements. Raises UpdateError."""
    before = _git("rev-parse", "HEAD")
    _git("pull", "--ff-only", "--quiet", timeout=120)
    if _git("diff", "--name-only", before, "HEAD", "--", "requirements.txt"):
        python = Path(sys.executable).with_name("python.exe")
        if not python.exists():
            python = Path(sys.executable)
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", "-r", "requirements.txt"],
            cwd=PROJECT, capture_output=True, text=True, timeout=600,
            creationflags=_NO_WINDOW)
        if result.returncode != 0:
            lines = (result.stderr or result.stdout).strip().splitlines()
            raise UpdateError("Updated, but installing the new requirements failed: "
                              + (lines[-1] if lines else "pip failed"))


if __name__ == "__main__":
    # python -m modeswitch.updater: say whether an update is waiting
    info = check()
    if not info:
        print("Up to date")
    else:
        print(f"{info.behind} new change(s):", *info.changes, sep="\n  ")
        if info.blocked:
            print(info.blocked)
