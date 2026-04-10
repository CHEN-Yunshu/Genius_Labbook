"""Full-text search and frontmatter filtering."""

from __future__ import annotations

import datetime
from pathlib import Path

from .config import LabbookConfig
from .entry import Entry
from .store import list_entries, load_entry


def search_entries(
    config: LabbookConfig,
    query: str | None = None,
    project: str | None = None,
    entry_type: str | None = None,
    tags: list[str] | None = None,
    after: datetime.date | None = None,
    before: datetime.date | None = None,
) -> list[tuple[Path, Entry]]:
    """Search entries by frontmatter fields and/or full-text query.

    Returns list of (path, entry) tuples, sorted by date descending.
    """
    paths = list_entries(config, project=project, after=after, before=before)

    results = []
    for path in paths:
        try:
            entry = load_entry(path)
        except (ValueError, KeyError):
            continue

        # Filter by type
        if entry_type and entry.entry_type != entry_type:
            continue

        # Filter by tags (all specified tags must be present)
        if tags and not all(t in entry.tags for t in tags):
            continue

        # Full-text search (case-insensitive)
        if query:
            text = f"{entry.title} {entry.body} {' '.join(entry.tags)}".lower()
            if query.lower() not in text:
                continue

        results.append((path, entry))

    return results
