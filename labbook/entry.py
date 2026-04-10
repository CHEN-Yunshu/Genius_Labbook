"""Entry data model and YAML frontmatter serialization."""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

import yaml


@dataclass
class Entry:
    date: datetime.date
    project: str
    title: str
    entry_type: str = "devlog"  # experiment | devlog | decision
    tags: list[str] = field(default_factory=list)
    body: str = ""
    figures: list[str] = field(default_factory=list)
    code_refs: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """Generate kebab-case slug from title."""
        s = self.title.lower()
        s = re.sub(r"[^a-z0-9\u4e00-\u9fff\s-]", "", s)
        s = re.sub(r"[\s]+", "-", s).strip("-")
        return s[:50]

    @property
    def filename(self) -> str:
        return f"{self.date.isoformat()}_{self.project}_{self.slug}.md"

    def to_markdown(self) -> str:
        """Serialize entry to markdown with YAML frontmatter."""
        meta = {
            "date": self.date.isoformat(),
            "project": self.project,
            "type": self.entry_type,
            "tags": self.tags,
            "title": self.title,
        }
        if self.figures:
            meta["figures"] = self.figures
        if self.code_refs:
            meta["code_refs"] = self.code_refs

        frontmatter = yaml.dump(
            meta, default_flow_style=False, allow_unicode=True, sort_keys=False
        )
        return f"---\n{frontmatter}---\n\n{self.body}\n"

    @classmethod
    def from_markdown(cls, text: str) -> Entry:
        """Parse entry from markdown with YAML frontmatter."""
        if not text.startswith("---"):
            raise ValueError("Entry must start with YAML frontmatter (---)")

        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Invalid frontmatter format")

        meta = yaml.safe_load(parts[1])
        body = parts[2].strip()

        date = meta.get("date")
        if isinstance(date, str):
            date = datetime.date.fromisoformat(date)

        return cls(
            date=date,
            project=meta.get("project", "unknown"),
            title=meta.get("title", ""),
            entry_type=meta.get("type", "devlog"),
            tags=meta.get("tags", []),
            body=body,
            figures=meta.get("figures", []),
            code_refs=meta.get("code_refs", []),
        )
