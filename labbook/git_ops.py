"""Git operations: commit and push using the user's global identity."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

from .config import LabbookConfig

console = Console()


def _run_git(config: LabbookConfig, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in the labbook root."""
    cmd = ["git", "-C", str(config.root)] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


def ensure_repo(config: LabbookConfig) -> None:
    """Initialize git repo if not already one."""
    git_dir = config.root / ".git"
    if git_dir.exists():
        return
    result = _run_git(config, "init")
    if result.returncode == 0:
        console.print("[green]Initialized git repository[/green]")
    else:
        console.print(f"[red]git init failed: {result.stderr}[/red]")


def commit_entry(
    config: LabbookConfig,
    paths: list[Path],
    message: str,
) -> str | None:
    """Stage files and commit. Returns commit SHA or None on failure."""
    ensure_repo(config)

    for p in paths:
        rel = p.relative_to(config.root)
        _run_git(config, "add", str(rel))

    result = _run_git(config, "commit", "-m", message)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "nothing to commit" in stderr:
            console.print("[dim]Nothing to commit[/dim]")
            return None
        console.print(f"[red]Commit failed: {stderr}[/red]")
        return None

    # Get commit SHA
    sha_result = _run_git(config, "rev-parse", "--short", "HEAD")
    sha = sha_result.stdout.strip()
    console.print(f"[green]Committed:[/green] {sha} {message}")
    return sha


def push(config: LabbookConfig, remote: str = "origin") -> bool:
    """Push to remote. Returns True on success."""
    ensure_repo(config)

    # Check if remote exists
    result = _run_git(config, "remote", "get-url", remote)
    if result.returncode != 0:
        console.print(
            f"[red]No remote '{remote}' configured.[/red]\n"
            f"  Add one with: git -C {config.root} remote add {remote} <url>"
        )
        return False

    result = _run_git(config, "push", remote, "HEAD")
    if result.returncode == 0:
        console.print(f"[green]Pushed to {remote}[/green]")
        return True
    else:
        console.print(f"[red]Push failed: {result.stderr.strip()}[/red]")
        return False


def get_status(config: LabbookConfig) -> str:
    """Get git status summary."""
    ensure_repo(config)
    result = _run_git(config, "status", "--short")
    return result.stdout.strip()
