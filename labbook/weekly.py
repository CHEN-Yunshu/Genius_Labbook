"""Weekly report generation for advisor meetings."""

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


def week_range(offset: int = 0) -> tuple[datetime.date, datetime.date]:
    """Return (monday, sunday) for the target week.

    offset=0 is current week, offset=-1 is last week, etc.
    """
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=offset)
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


def _git_log_range(project_path: str, since: datetime.date, until: datetime.date) -> list[str]:
    """Get git commits in a date range."""
    try:
        result = subprocess.run(
            ["git", "-C", project_path, "log",
             f"--since={since.isoformat()}",
             f"--until={(until + datetime.timedelta(days=1)).isoformat()}",
             "--oneline", "--no-merges"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def generate_weekly(
    config: LabbookConfig,
    monday: datetime.date,
    sunday: datetime.date,
) -> str:
    """Generate a structured weekly report as markdown."""
    lines = [
        f"# Weekly Report: {monday.isoformat()} ~ {sunday.isoformat()}",
        "",
    ]

    # Collect all entries for the week
    all_entries = search_entries(
        config, after=monday, before=sunday + datetime.timedelta(days=1)
    )

    # Overall summary
    if all_entries:
        lines.append(f"**{len(all_entries)} entries** across the week.")
        lines.append("")

    # Per-project sections
    for proj_name, proj_cfg in config.projects.items():
        proj_entries = [(p, e) for p, e in all_entries if e.project == proj_name]
        commits = _git_log_range(proj_cfg.path, monday, sunday) if proj_cfg.has_git else []

        # Completed todos
        todos = _load_todos(config, proj_name)
        done_this_week = [
            t for t in todos
            if t.get("status") == "done"
            and monday.isoformat() <= t.get("done_date", "") <= sunday.isoformat()
        ]
        pending = [t for t in todos if t.get("status") == "pending"]

        # Skip projects with no activity
        if not proj_entries and not commits and not done_this_week:
            continue

        lines.append(f"## {proj_name}")
        lines.append("")

        # Entries
        if proj_entries:
            lines.append("### Journal Entries")
            lines.append("")
            for path, entry in proj_entries:
                tags = f" `{'` `'.join(entry.tags)}`" if entry.tags else ""
                lines.append(f"- **{entry.date.isoformat()}** [{entry.entry_type}] {entry.title}{tags}")
            lines.append("")

        # Commits
        if commits:
            lines.append(f"### Git Commits ({len(commits)})")
            lines.append("")
            for c in commits[:15]:
                lines.append(f"- {c}")
            if len(commits) > 15:
                lines.append(f"- ... and {len(commits) - 15} more")
            lines.append("")

        # Completed todos
        if done_this_week:
            lines.append("### Completed")
            lines.append("")
            for t in done_this_week:
                lines.append(f"- [x] {t['task']}")
            lines.append("")

        # Pending todos (top 5)
        if pending:
            lines.append("### Pending")
            lines.append("")
            for t in pending[:5]:
                lines.append(f"- [ ] {t['task']}")
            if len(pending) > 5:
                lines.append(f"- ... and {len(pending) - 5} more")
            lines.append("")

    # Editable sections
    lines.extend([
        "## Highlights",
        "",
        "- ",
        "",
        "## Next Week",
        "",
        "- ",
        "",
    ])

    return "\n".join(lines)


def save_weekly(config: LabbookConfig, content: str, monday: datetime.date) -> Path:
    """Save weekly report."""
    reports_dir = config.root / "reports"
    reports_dir.mkdir(exist_ok=True)
    path = reports_dir / f"weekly_{monday.isoformat()}.md"
    path.write_text(content, encoding="utf-8")
    return path


def show_weekly(
    config: LabbookConfig,
    monday: datetime.date,
    sunday: datetime.date,
) -> None:
    """Generate and display weekly report."""
    content = generate_weekly(config, monday, sunday)
    console.print(Markdown(content))
