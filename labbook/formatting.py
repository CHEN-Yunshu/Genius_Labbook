"""Rich terminal rendering for labbook entries."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from .entry import Entry

console = Console()


def print_entry_list(entries: list[tuple[Path, Entry]], title: str = "Entries") -> None:
    """Print a table of entries."""
    if not entries:
        console.print("[dim]No entries found.[/dim]")
        return

    table = Table(title=title, show_lines=False)
    table.add_column("Date", style="cyan", width=10)
    table.add_column("Project", style="green", width=16)
    table.add_column("Type", style="yellow", width=10)
    table.add_column("Title", style="white")
    table.add_column("Tags", style="dim")

    for _path, entry in entries:
        tags = ", ".join(entry.tags) if entry.tags else ""
        table.add_row(
            entry.date.isoformat(),
            entry.project,
            entry.entry_type,
            entry.title,
            tags,
        )

    console.print(table)


def print_entry_detail(entry: Entry, path: Path | None = None) -> None:
    """Print full entry with rich markdown rendering."""
    header = f"[bold cyan]{entry.date.isoformat()}[/bold cyan] "
    header += f"[bold green]{entry.project}[/bold green] "
    header += f"[yellow]({entry.entry_type})[/yellow]"
    console.print(header)
    console.print(f"[bold]{entry.title}[/bold]")

    if entry.tags:
        tags = " ".join(f"[dim]#{t}[/dim]" for t in entry.tags)
        console.print(f"Tags: {tags}")
    if entry.figures:
        console.print(f"Figures: {len(entry.figures)} attached")
    if entry.code_refs:
        console.print(f"Code refs: {len(entry.code_refs)}")
    if path:
        console.print(f"[dim]File: {path}[/dim]")

    console.print()
    if entry.body:
        console.print(Markdown(entry.body))
    else:
        console.print("[dim](empty body)[/dim]")


def print_status(
    total_entries: int,
    recent: list[tuple[Path, Entry]],
    projects: list[str],
) -> None:
    """Print labbook status overview."""
    console.print(f"[bold]Labbook Status[/bold]")
    console.print(f"  Entries: [cyan]{total_entries}[/cyan]")
    console.print(f"  Projects: [green]{', '.join(projects)}[/green]")
    console.print()
    if recent:
        console.print("[bold]Recent entries:[/bold]")
        print_entry_list(recent, title="Recent")
