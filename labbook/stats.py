"""Labbook statistics dashboard."""

from __future__ import annotations

import datetime
from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import LabbookConfig
from .store import list_entries, load_entry


def compute_stats(config: LabbookConfig) -> dict:
    """Compute all stats in a single pass over entries."""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # 8 weeks ago (Monday)
    eight_weeks_ago = monday - datetime.timedelta(weeks=7)

    paths = list_entries(config)
    total = 0
    this_week = 0
    this_month = 0
    project_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    entry_dates: set[datetime.date] = set()
    weekly_buckets: Counter[int] = Counter()  # week_offset -> count

    for p in paths:
        try:
            entry = load_entry(p)
        except (ValueError, KeyError):
            continue

        total += 1
        d = entry.date
        entry_dates.add(d)
        project_counts[d and entry.project] += 1
        project_counts[entry.project] += 0  # ensure key exists
        # fix: only count project properly
        tag_counts.update(entry.tags)

        if d >= monday:
            this_week += 1
        if d >= month_start:
            this_month += 1

        # Weekly bucket (0 = current week, -1 = last week, etc.)
        if d >= eight_weeks_ago:
            week_offset = (d - monday).days // 7
            weekly_buckets[week_offset] += 1

    # Fix project counter (was double counting)
    project_counts = Counter()
    for p in paths:
        try:
            entry = load_entry(p)
            project_counts[entry.project] += 1
        except (ValueError, KeyError):
            continue

    # Streak: consecutive days with entries, ending today or yesterday
    streak = 0
    check = today
    # Allow streak to start from yesterday if no entry today
    if check not in entry_dates and (check - datetime.timedelta(days=1)) in entry_dates:
        check = check - datetime.timedelta(days=1)
    while check in entry_dates:
        streak += 1
        check -= datetime.timedelta(days=1)

    return {
        "total": total,
        "this_week": this_week,
        "this_month": this_month,
        "streak": streak,
        "project_counts": project_counts,
        "top_tags": tag_counts.most_common(10),
        "weekly_buckets": weekly_buckets,
        "week_monday": monday,
    }


def render_stats(console: Console, stats: dict) -> None:
    """Render statistics dashboard to terminal."""
    # Summary panel
    streak_str = f"{stats['streak']} days" if stats['streak'] > 0 else "0"
    summary = (
        f"[cyan]Total entries:[/cyan]  {stats['total']}\n"
        f"[cyan]This week:[/cyan]      {stats['this_week']}\n"
        f"[cyan]This month:[/cyan]     {stats['this_month']}\n"
        f"[cyan]Streak:[/cyan]         {streak_str}"
    )
    console.print(Panel(summary, title="[bold]Labbook Stats[/bold]", border_style="green"))

    # Per-project table
    if stats["project_counts"]:
        table = Table(title="Entries by Project", show_lines=False)
        table.add_column("Project", style="green")
        table.add_column("Entries", style="cyan", justify="right")
        for proj, count in stats["project_counts"].most_common():
            table.add_row(proj, str(count))
        console.print(table)

    # Top tags
    if stats["top_tags"]:
        table = Table(title="Top Tags", show_lines=False)
        table.add_column("Tag", style="yellow")
        table.add_column("Count", style="cyan", justify="right")
        for tag, count in stats["top_tags"]:
            table.add_row(f"#{tag}", str(count))
        console.print(table)

    # Weekly activity (last 8 weeks)
    monday = stats["week_monday"]
    buckets = stats["weekly_buckets"]

    table = Table(title="Weekly Activity (last 8 weeks)", show_lines=False)
    table.add_column("Week", style="dim", width=24)
    table.add_column("Entries", justify="right", width=6)
    table.add_column("", style="green")

    max_count = max(buckets.values()) if buckets else 1

    for offset in range(-7, 1):
        week_start = monday + datetime.timedelta(weeks=offset)
        week_end = week_start + datetime.timedelta(days=6)
        count = buckets.get(offset, 0)
        bar_len = int((count / max_count) * 30) if max_count > 0 and count > 0 else 0
        bar = "\u2588" * bar_len
        label = f"{week_start.strftime('%m/%d')} - {week_end.strftime('%m/%d')}"
        if offset == 0:
            label += " (now)"
        table.add_row(label, str(count), bar)

    console.print(table)
