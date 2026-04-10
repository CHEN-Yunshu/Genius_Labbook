"""Project pathway/roadmap management — living documents per project."""

from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from .config import LabbookConfig

console = Console()

PATHWAY_TEMPLATE = """---
project: {project}
updated: {date}
---

# {project} — Project Pathway

## Current Phase


## Milestones

- [ ] Milestone 1
- [ ] Milestone 2

## Technical Design

### Architecture


### Key Decisions


## References

"""


def _pathways_dir(config: LabbookConfig) -> Path:
    d = config.root / "pathways"
    d.mkdir(exist_ok=True)
    return d


def pathway_path(config: LabbookConfig, project: str) -> Path:
    return _pathways_dir(config) / f"{project}.md"


def init_pathway(config: LabbookConfig, project: str) -> Path:
    """Create pathway file from template if it doesn't exist."""
    path = pathway_path(config, project)
    if not path.exists():
        content = PATHWAY_TEMPLATE.format(
            project=project,
            date=datetime.date.today().isoformat(),
        )
        path.write_text(content, encoding="utf-8")
        console.print(f"[green]Created pathway:[/green] {path.relative_to(config.root)}")
    return path


def show_pathway(config: LabbookConfig, project: str) -> None:
    """Display pathway in terminal."""
    path = pathway_path(config, project)
    if not path.exists():
        console.print(f"[dim]No pathway for '{project}'. Use --edit to create one.[/dim]")
        return

    text = path.read_text(encoding="utf-8")
    # Strip YAML frontmatter for display
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2].strip()

    console.print(f"[bold cyan]{project}[/bold cyan] pathway")
    console.print(f"[dim]{path}[/dim]\n")
    console.print(Markdown(text))


def edit_pathway(config: LabbookConfig, project: str) -> Path:
    """Open pathway in editor (create if needed)."""
    path = init_pathway(config, project)
    editor = os.environ.get("EDITOR", config.editor)
    subprocess.run([editor, str(path)])
    return path


def list_pathways(config: LabbookConfig) -> None:
    """List all existing pathways."""
    pathways_dir = _pathways_dir(config)
    files = sorted(pathways_dir.glob("*.md"))
    if not files:
        console.print("[dim]No pathways yet. Create one with: lab pathway <project> --edit[/dim]")
        return

    console.print("[bold]Project Pathways:[/bold]")
    for f in files:
        name = f.stem
        stat = f.stat()
        mtime = datetime.date.fromtimestamp(stat.st_mtime).isoformat()
        size_kb = stat.st_size / 1024
        console.print(f"  [green]{name}[/green]  ({size_kb:.1f}KB, updated {mtime})")
