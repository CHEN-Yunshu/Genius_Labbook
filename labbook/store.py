"""Storage layer: read/write entries to disk."""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml

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


def _read_project_from_frontmatter(path: Path) -> str | None:
    """Read just the `project` field from YAML frontmatter without loading the body.

    Filename-based parsing breaks for project names containing `_` (the same
    separator used in filenames), so we authoritatively read the frontmatter.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        meta = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None
    return meta.get("project") if isinstance(meta, dict) else None


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
        try:
            file_date = datetime.date.fromisoformat(p.stem[:10])
        except ValueError:
            continue

        if after and file_date < after:
            continue
        if before and file_date > before:
            continue

        if project and _read_project_from_frontmatter(p) != project:
            continue

        results.append(p)

    return results
