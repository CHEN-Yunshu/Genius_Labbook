"""Daily/weekly work report generation with project cross-references."""

from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from .config import LabbookConfig
from .search import search_entries
from .todo import _load_todos

console = Console()


def _git_log_today(project_path: str, date: datetime.date) -> list[str]:
    """Get git commits from a project on a given date."""
    try:
        result = subprocess.run(
            ["git", "-C", project_path, "log",
             f"--since={date.isoformat()}",
             f"--until={(date + datetime.timedelta(days=1)).isoformat()}",
             "--oneline", "--no-merges"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def _find_recent_results(project_path: str, date: datetime.date) -> list[str]:
    """Find result files modified on a given date."""
    results = []
    for dirpath, _dirs, files in os.walk(project_path):
        # Only check common result directories
        rel = os.path.relpath(dirpath, project_path)
        if not any(k in rel for k in ("results", "reports", "figures", "paper", "logs", "output")):
            continue
        for f in files:
            fpath = os.path.join(dirpath, f)
            try:
                mtime = datetime.date.fromtimestamp(os.path.getmtime(fpath))
                if mtime == date:
                    results.append(os.path.relpath(fpath, project_path))
            except OSError:
                continue
    return results[:30]  # Cap to avoid huge lists


def generate_report(
    config: LabbookConfig,
    date: datetime.date | None = None,
    days: int = 1,
) -> str:
    """Generate a daily/multi-day work report as markdown."""
    if date is None:
        date = datetime.date.today()

    start_date = date - datetime.timedelta(days=days - 1)
    end_date = date

    lines = [
        f"# Work Report: {start_date.isoformat()}" + (
            f" ~ {end_date.isoformat()}" if days > 1 else ""
        ),
        "",
    ]

    # 1. Journal entries for the period
    entries = search_entries(config, after=start_date, before=end_date + datetime.timedelta(days=1))
    if entries:
        lines.append("## Journal Entries")
        lines.append("")
        for path, entry in entries:
            tags = f" `{'` `'.join(entry.tags)}`" if entry.tags else ""
            lines.append(f"- **[{entry.project}]** {entry.title} ({entry.entry_type}){tags}")
            if entry.figures:
                for fig in entry.figures:
                    lines.append(f"  - Figure: `{fig}`")
            if entry.code_refs:
                for ref in entry.code_refs:
                    lines.append(f"  - Code: `{ref}`")
        lines.append("")

    # 2. Per-project activity
    lines.append("## Project Activity")
    lines.append("")

    for proj_name, proj_cfg in config.projects.items():
        proj_lines = []

        # Git commits
        if proj_cfg.has_git:
            for d in range(days):
                check_date = start_date + datetime.timedelta(days=d)
                commits = _git_log_today(proj_cfg.path, check_date)
                for c in commits:
                    proj_lines.append(f"  - commit: {c}")

        # Recent result files
        for d in range(days):
            check_date = start_date + datetime.timedelta(days=d)
            results = _find_recent_results(proj_cfg.path, check_date)
            for r in results[:10]:
                proj_lines.append(f"  - result: `{r}`")

        # Pending todos
        todos = _load_todos(config, proj_name)
        pending = [t for t in todos if t.get("status") == "pending"]
        done_today = [
            t for t in todos
            if t.get("status") == "done" and t.get("done_date", "") >= start_date.isoformat()
        ]

        for t in done_today:
            proj_lines.append(f"  - [x] {t['task']}")
        for t in pending[:5]:
            proj_lines.append(f"  - [ ] {t['task']}")

        if proj_lines:
            lines.append(f"### {proj_name}")
            lines.append("")
            lines.extend(proj_lines)
            lines.append("")

    return "\n".join(lines)


def save_report(config: LabbookConfig, content: str, date: datetime.date) -> Path:
    """Save report to entries as a special 'report' type."""
    reports_dir = config.root / "reports"
    reports_dir.mkdir(exist_ok=True)
    path = reports_dir / f"{date.isoformat()}_daily.md"
    path.write_text(content, encoding="utf-8")
    return path


def show_report(config: LabbookConfig, date: datetime.date | None = None, days: int = 1) -> None:
    """Generate and display a work report."""
    if date is None:
        date = datetime.date.today()

    content = generate_report(config, date, days)
    console.print(Markdown(content))

    # Save
    path = save_report(config, content, date)
    console.print(f"\n[dim]Saved: {path.relative_to(config.root)}[/dim]")
