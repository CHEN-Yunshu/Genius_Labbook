"""Reproducibility snapshots — capture and restore experiment environments."""

from __future__ import annotations

import datetime
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import LabbookConfig
from .store import list_entries, load_entry

console = Console()


@dataclass
class ReproSnapshot:
    timestamp: str
    project: str
    git_sha: str | None = None
    git_branch: str | None = None
    git_dirty: bool = False
    git_diff_summary: str | None = None
    python_version: str = ""
    conda_env: str | None = None
    pip_packages: list[str] = field(default_factory=list)
    gpu_info: str | None = None
    run_command: str | None = None

    def to_dict(self) -> dict:
        d = {
            "timestamp": self.timestamp,
            "project": self.project,
            "python_version": self.python_version,
        }
        if self.git_sha:
            d["git"] = {
                "sha": self.git_sha,
                "branch": self.git_branch,
                "dirty": self.git_dirty,
            }
            if self.git_diff_summary:
                d["git"]["diff_summary"] = self.git_diff_summary
        if self.conda_env:
            d["conda_env"] = self.conda_env
        if self.pip_packages:
            d["pip_packages"] = self.pip_packages
        if self.gpu_info:
            d["gpu_info"] = self.gpu_info
        if self.run_command:
            d["run_command"] = self.run_command
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ReproSnapshot:
        git = data.get("git", {})
        return cls(
            timestamp=data.get("timestamp", ""),
            project=data.get("project", ""),
            git_sha=git.get("sha"),
            git_branch=git.get("branch"),
            git_dirty=git.get("dirty", False),
            git_diff_summary=git.get("diff_summary"),
            python_version=data.get("python_version", ""),
            conda_env=data.get("conda_env"),
            pip_packages=data.get("pip_packages", []),
            gpu_info=data.get("gpu_info"),
            run_command=data.get("run_command"),
        )


def _run_cmd(cmd: list[str], cwd: str | None = None, timeout: int = 15) -> str | None:
    """Run a command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def capture_snapshot(
    config: LabbookConfig,
    project: str,
    run_command: str | None = None,
) -> ReproSnapshot:
    """Capture current environment snapshot for a project."""
    proj_cfg = config.projects[project]
    proj_path = proj_cfg.path
    now = datetime.datetime.now().isoformat(timespec="seconds")

    snapshot = ReproSnapshot(timestamp=now, project=project)

    # Git info
    if proj_cfg.has_git and Path(proj_path).exists():
        snapshot.git_sha = _run_cmd(["git", "-C", proj_path, "rev-parse", "HEAD"])
        snapshot.git_branch = _run_cmd(["git", "-C", proj_path, "branch", "--show-current"])
        porcelain = _run_cmd(["git", "-C", proj_path, "status", "--porcelain"])
        snapshot.git_dirty = bool(porcelain)
        if snapshot.git_dirty:
            diff_stat = _run_cmd(["git", "-C", proj_path, "diff", "--stat"])
            if diff_stat:
                # Last line of diff --stat is the summary
                lines = diff_stat.strip().splitlines()
                snapshot.git_diff_summary = lines[-1].strip() if lines else None

    # Python version
    snapshot.python_version = _run_cmd(["python", "--version"]) or ""

    # Conda env
    conda_env = os.environ.get("CONDA_DEFAULT_ENV")
    if conda_env:
        snapshot.conda_env = conda_env

    # Pip packages (compact: only non-standard-lib)
    pip_output = _run_cmd(["pip", "list", "--format=freeze"], timeout=30)
    if pip_output:
        snapshot.pip_packages = pip_output.splitlines()

    # GPU info
    gpu = _run_cmd([
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ])
    if gpu:
        snapshot.gpu_info = gpu

    snapshot.run_command = run_command
    return snapshot


def _reproduce_dir(config: LabbookConfig) -> Path:
    d = config.root / "reproduce"
    d.mkdir(exist_ok=True)
    return d


def save_snapshot(config: LabbookConfig, snapshot: ReproSnapshot) -> Path:
    """Save snapshot as YAML."""
    proj_dir = _reproduce_dir(config) / snapshot.project
    proj_dir.mkdir(parents=True, exist_ok=True)

    sha_short = snapshot.git_sha[:7] if snapshot.git_sha else "nosha"
    date = snapshot.timestamp[:10]
    path = proj_dir / f"{date}_{sha_short}.reproduce.yaml"

    # Handle duplicates
    if path.exists():
        stem = path.stem
        suffix = 2
        while path.exists():
            path = proj_dir / f"{stem}_{suffix}.yaml"
            suffix += 1

    with open(path, "w") as f:
        yaml.dump(snapshot.to_dict(), f, default_flow_style=False, sort_keys=False)

    return path


def load_snapshot(path: Path) -> ReproSnapshot:
    """Load snapshot from YAML."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return ReproSnapshot.from_dict(data)


def find_snapshot(config: LabbookConfig, query: str) -> Path | None:
    """Find a snapshot by entry ID, project name, or direct path."""
    # Direct path
    query_path = Path(query)
    if query_path.exists() and query_path.suffix in (".yaml", ".yml"):
        return query_path

    # Search in reproduce/
    repro_dir = _reproduce_dir(config)
    if not repro_dir.exists():
        return None

    matches = sorted(repro_dir.rglob("*.yaml"), reverse=True)
    for p in matches:
        if query in p.name or query in p.parent.name:
            return p

    # Try matching by entry filename -> project + date
    entries_paths = list_entries(config)
    for ep in entries_paths:
        if query in ep.name:
            try:
                entry = load_entry(ep)
            except (ValueError, KeyError):
                continue
            # Find closest reproduce snapshot for this project + date
            proj_dir = repro_dir / entry.project
            if proj_dir.exists():
                date_str = entry.date.isoformat()
                for rp in sorted(proj_dir.glob("*.yaml"), reverse=True):
                    if date_str in rp.name:
                        return rp
                # Return most recent for this project
                snapshots = sorted(proj_dir.glob("*.yaml"), reverse=True)
                if snapshots:
                    return snapshots[0]
            break

    return None


def format_reproduce_commands(snapshot: ReproSnapshot) -> str:
    """Generate shell commands to recreate the environment."""
    lines = ["#!/bin/bash", f"# Reproduce: {snapshot.project} @ {snapshot.timestamp}", ""]

    if snapshot.git_sha:
        lines.append(f"# Git checkout")
        lines.append(f"git checkout {snapshot.git_sha}")
        lines.append("")

    if snapshot.conda_env:
        lines.append(f"# Conda environment")
        lines.append(f"conda activate {snapshot.conda_env}")
        lines.append("")

    if snapshot.pip_packages:
        lines.append("# Install dependencies")
        lines.append("pip install \\")
        for pkg in snapshot.pip_packages:
            lines.append(f"  {pkg} \\")
        # Remove trailing backslash from last line
        lines[-1] = lines[-1].rstrip(" \\")
        lines.append("")

    if snapshot.run_command:
        lines.append("# Run")
        lines.append(snapshot.run_command)
        lines.append("")

    return "\n".join(lines)


def render_snapshot(console: Console, snapshot: ReproSnapshot) -> None:
    """Display snapshot as a Rich panel."""
    table = Table(show_header=False, show_lines=False, pad_edge=False, box=None)
    table.add_column("Key", style="cyan", width=16)
    table.add_column("Value")

    table.add_row("Project", snapshot.project)
    table.add_row("Timestamp", snapshot.timestamp)
    table.add_row("Python", snapshot.python_version)

    if snapshot.git_sha:
        dirty = " [red](dirty)[/red]" if snapshot.git_dirty else " [green](clean)[/green]"
        table.add_row("Git SHA", f"{snapshot.git_sha[:12]}{dirty}")
        if snapshot.git_branch:
            table.add_row("Branch", snapshot.git_branch)
        if snapshot.git_diff_summary:
            table.add_row("Changes", snapshot.git_diff_summary)

    if snapshot.conda_env:
        table.add_row("Conda Env", snapshot.conda_env)

    table.add_row("Pip Packages", f"{len(snapshot.pip_packages)} packages")

    if snapshot.gpu_info:
        table.add_row("GPU", snapshot.gpu_info)

    if snapshot.run_command:
        table.add_row("Command", snapshot.run_command)

    console.print(Panel(table, title="[bold]Reproducibility Snapshot[/bold]", border_style="blue"))
