"""Auto-scan project directories and record activity."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .config import LabbookConfig, ProjectConfig
from .entry import Entry
from .git_ops import commit_entry
from .store import save_entry

console = Console()

# Directories to scan for result/output files
RESULT_PATTERNS = ("results", "reports", "figures", "paper", "output", "outputs",
                   "logs", "checkpoints", "visualizations", "nature_panels")

# Extensions considered as "results"
RESULT_EXTENSIONS = {".csv", ".json", ".png", ".jpg", ".pdf", ".svg",
                     ".log", ".md", ".xlsx", ".txt", ".yaml", ".yml"}

# Skip these when scanning
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache",
             "node_modules", ".cache", "wandb", ".eggs", ".tox"}


@dataclass
class ProjectActivity:
    project: str
    commits: list[str] = field(default_factory=list)
    new_files: list[tuple[str, int]] = field(default_factory=list)  # (relpath, size)
    modified_files: list[tuple[str, int]] = field(default_factory=list)
    new_logs: list[str] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)

    @property
    def has_activity(self) -> bool:
        return bool(self.commits or self.new_files or self.modified_files or self.new_logs)

    @property
    def total_changes(self) -> int:
        return len(self.commits) + len(self.new_files) + len(self.modified_files) + len(self.new_logs)


def _state_path(config: LabbookConfig) -> Path:
    return config.root / ".scan_state.json"


def _load_state(config: LabbookConfig) -> dict:
    path = _state_path(config)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def _save_state(config: LabbookConfig, state: dict) -> None:
    path = _state_path(config)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def _git_commits_since(project_path: str, since: str) -> list[str]:
    """Get git commits since a timestamp."""
    try:
        result = subprocess.run(
            ["git", "-C", project_path, "log",
             f"--since={since}", "--oneline", "--no-merges",
             "--format=%h %s"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def _find_changed_files(
    project_path: str,
    since_ts: float,
    results_dir: str | None = None,
    logs_dir: str | None = None,
) -> tuple[list[tuple[str, int]], list[tuple[str, int]], list[str]]:
    """Find new and modified files since a timestamp.

    Returns (new_files, modified_files, new_logs).
    """
    root = Path(project_path)
    new_files = []
    modified_files = []
    new_logs = []

    # Determine which directories to scan
    scan_dirs = []
    if results_dir:
        scan_dirs.append(root / results_dir)
    if logs_dir:
        scan_dirs.append(root / logs_dir)

    # Also scan known result directory names at top level
    for name in RESULT_PATTERNS:
        candidate = root / name
        if candidate.is_dir() and candidate not in scan_dirs:
            scan_dirs.append(candidate)

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue

        for dirpath, dirs, files in os.walk(scan_dir):
            # Skip junk directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for f in files:
                fpath = Path(dirpath) / f
                ext = fpath.suffix.lower()
                if ext not in RESULT_EXTENSIONS:
                    continue

                try:
                    stat = fpath.stat()
                except OSError:
                    continue

                rel = str(fpath.relative_to(root))
                size = stat.st_size

                if stat.st_mtime > since_ts:
                    # Check if it was created or modified
                    if stat.st_ctime > since_ts:
                        new_files.append((rel, size))
                        if ext == ".log":
                            new_logs.append(rel)
                    else:
                        modified_files.append((rel, size))
                        if ext == ".log":
                            new_logs.append(rel)

    # Cap to avoid huge lists
    return new_files[:50], modified_files[:50], new_logs[:20]


def scan_project(
    config: LabbookConfig,
    proj_name: str,
    proj_cfg: ProjectConfig,
    since_ts: float,
) -> ProjectActivity:
    """Scan a single project for activity since last scan."""
    activity = ProjectActivity(project=proj_name)

    since_iso = datetime.datetime.fromtimestamp(since_ts).isoformat()

    # Git commits
    if proj_cfg.has_git:
        activity.commits = _git_commits_since(proj_cfg.path, since_iso)

    # File changes
    new, modified, logs = _find_changed_files(
        proj_cfg.path,
        since_ts,
        proj_cfg.results_dir,
        proj_cfg.logs_dir,
    )
    activity.new_files = new
    activity.modified_files = modified
    activity.new_logs = logs

    # Build summary
    if activity.commits:
        activity.summary_lines.append(f"**{len(activity.commits)} commits**")
    if activity.new_files:
        activity.summary_lines.append(f"**{len(activity.new_files)} new result files**")
    if activity.modified_files:
        activity.summary_lines.append(f"**{len(activity.modified_files)} modified files**")

    return activity


def scan_all(
    config: LabbookConfig,
    project: str | None = None,
    since_hours: int | None = None,
) -> list[ProjectActivity]:
    """Scan all (or one) project for activity.

    Uses last scan timestamp by default, or --since-hours to override.
    """
    state = _load_state(config)
    now = datetime.datetime.now().timestamp()

    if since_hours is not None:
        since_ts = now - since_hours * 3600
    else:
        since_ts = state.get("last_scan", now - 24 * 3600)  # Default: last 24h

    projects = (
        {project: config.projects[project]}
        if project and project in config.projects
        else config.projects
    )

    activities = []
    for name, cfg in projects.items():
        if not Path(cfg.path).exists():
            continue
        activity = scan_project(config, name, cfg, since_ts)
        if activity.has_activity:
            activities.append(activity)

    # Update last scan time
    state["last_scan"] = now
    state["last_scan_readable"] = datetime.datetime.now().isoformat()
    _save_state(config, state)

    return activities


def print_scan_results(activities: list[ProjectActivity]) -> None:
    """Print scan results to console."""
    if not activities:
        console.print("[dim]No new activity detected since last scan.[/dim]")
        return

    total = sum(a.total_changes for a in activities)
    console.print(f"[bold]Scan: {total} changes across {len(activities)} projects[/bold]\n")

    for act in activities:
        console.print(f"[bold green]{act.project}[/bold green] ({act.total_changes} changes)")

        if act.commits:
            console.print(f"  [cyan]Commits ({len(act.commits)}):[/cyan]")
            for c in act.commits[:10]:
                console.print(f"    {c}")

        if act.new_files:
            console.print(f"  [yellow]New files ({len(act.new_files)}):[/yellow]")
            for path, size in act.new_files[:10]:
                console.print(f"    + {path}")
            if len(act.new_files) > 10:
                console.print(f"    ... and {len(act.new_files) - 10} more")

        if act.modified_files:
            console.print(f"  [blue]Modified ({len(act.modified_files)}):[/blue]")
            for path, size in act.modified_files[:10]:
                console.print(f"    ~ {path}")
            if len(act.modified_files) > 10:
                console.print(f"    ... and {len(act.modified_files) - 10} more")

        console.print()


def create_scan_entries(
    config: LabbookConfig,
    activities: list[ProjectActivity],
    auto_commit: bool = True,
) -> list[Path]:
    """Create journal entries from scan results."""
    paths = []

    for act in activities:
        if not act.has_activity:
            continue

        # Build body
        body_parts = [f"## Auto-scan Summary\n"]

        if act.commits:
            body_parts.append("### Git Commits\n")
            for c in act.commits:
                body_parts.append(f"- `{c}`")
            body_parts.append("")

        if act.new_files:
            body_parts.append(f"### New Result Files ({len(act.new_files)})\n")
            for path, _size in act.new_files[:20]:
                body_parts.append(f"- `{path}`")
            if len(act.new_files) > 20:
                body_parts.append(f"- ... and {len(act.new_files) - 20} more")
            body_parts.append("")

        if act.modified_files:
            body_parts.append(f"### Modified Files ({len(act.modified_files)})\n")
            for path, _size in act.modified_files[:20]:
                body_parts.append(f"- `{path}`")
            if len(act.modified_files) > 20:
                body_parts.append(f"- ... and {len(act.modified_files) - 20} more")
            body_parts.append("")

        summary = ", ".join(act.summary_lines) if act.summary_lines else "activity detected"
        title = f"[scan] {summary}"

        entry = Entry(
            date=datetime.date.today(),
            project=act.project,
            title=title,
            entry_type="devlog",
            tags=["auto-scan"],
            body="\n".join(body_parts),
        )

        path = save_entry(config, entry)
        paths.append(path)
        console.print(f"[green]Entry:[/green] {path.relative_to(config.root)}")

    if auto_commit and paths:
        commit_entry(
            config, paths,
            f"lab: auto-scan {len(activities)} projects ({datetime.date.today().isoformat()})",
        )

    return paths
