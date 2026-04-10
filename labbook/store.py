"""Storage layer: read/write entries to disk."""

from __future__ import annotations

import datetime
from pathlib import Path

from .config import LabbookConfig
from .entry import Entry


def entry_dir(config: LabbookConfig, date: datetime.date) -> Path:
    """Return entries/YYYY/MM/ directory for a given date."""
    return config.entries_dir / str(date.year) / f"{date.month:02d}"


def save_entry(config: LabbookConfig, entry: Entry) -> Path:
    """Write entry to disk. Returns the file path."""
    d = entry_dir(config, entry.date)
    d.mkdir(parents=True, exist_ok=True)

    path = d / entry.filename
    # Handle duplicate filenames
    if path.exists():
        stem = path.stem
        suffix = 2
        while path.exists():
            path = d / f"{stem}_{suffix}.md"
            suffix += 1

    path.write_text(entry.to_markdown(), encoding="utf-8")
    return path


def load_entry(path: Path) -> Entry:
    """Load an entry from a markdown file."""
    text = path.read_text(encoding="utf-8")
    return Entry.from_markdown(text)


def list_entries(
    config: LabbookConfig,
    project: str | None = None,
    after: datetime.date | None = None,
    before: datetime.date | None = None,
) -> list[Path]:
    """List entry files, optionally filtered by project/date range.

    Returns paths sorted by filename (date descending).
    """
    entries_dir = config.entries_dir
    if not entries_dir.exists():
        return []

    paths = sorted(entries_dir.rglob("*.md"), reverse=True)

    results = []
    for p in paths:
        name = p.stem
        # Filter by project: filename format is YYYY-MM-DD_<project>_<slug>
        if project:
            parts = name.split("_", 2)
            if len(parts) >= 2 and parts[1] != project:
                continue

        # Filter by date range
        try:
            date_str = name[:10]  # YYYY-MM-DD
            file_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            continue

        if after and file_date < after:
            continue
        if before and file_date > before:
            continue

        results.append(p)

    return results
