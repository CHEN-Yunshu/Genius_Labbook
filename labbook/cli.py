"""Typer CLI application: the `lab` command."""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from .archive import archive_figure
from .config import load_config
from .entry import Entry
from .formatting import print_entry_detail, print_entry_list, print_status
from .git_ops import commit_entry, get_status, push as git_push
from .search import search_entries
from .store import list_entries, load_entry, save_entry

app = typer.Typer(
    name="lab",
    help="Research development journal — record experiments, code, and visualizations.",
    no_args_is_help=True,
)
console = Console()

VALID_TYPES = ["experiment", "devlog", "decision", "design"]


def _today() -> datetime.date:
    return datetime.date.today()


def _validate_project(project: str) -> None:
    config = load_config()
    if project not in config.projects:
        names = ", ".join(config.projects.keys())
        console.print(f"[red]Unknown project '{project}'. Known: {names}[/red]")
        raise typer.Exit(1)


def _load_template(entry_type: str) -> str:
    config = load_config()
    tmpl_path = config.templates_dir / f"{entry_type}.md"
    if tmpl_path.exists():
        return tmpl_path.read_text(encoding="utf-8")
    return ""


def _open_in_editor(path: Path) -> None:
    config = load_config()
    editor = os.environ.get("EDITOR", config.editor)
    subprocess.run([editor, str(path)])


# ─── Init ───────────────────────────────────────────────────────────────────


@app.command()
def init(
    path: Annotated[Optional[Path], typer.Argument(help="Directory to initialize (default: current)")] = None,
):
    """Initialize a new labbook in the current or specified directory."""
    root = Path(path).resolve() if path else Path.cwd().resolve()

    if (root / "config.yaml").exists():
        console.print(f"[yellow]Labbook already initialized at {root}[/yellow]")
        raise typer.Exit(0)

    root.mkdir(parents=True, exist_ok=True)

    # Create directory structure
    for d in ["entries", "figures", "todos", "pathways", "reports", "templates"]:
        (root / d).mkdir(exist_ok=True)

    # Copy templates from package
    pkg_templates = Path(__file__).parent.parent / "templates"
    if pkg_templates.is_dir():
        for tmpl in pkg_templates.glob("*.md"):
            dest = root / "templates" / tmpl.name
            if not dest.exists():
                shutil.copy2(tmpl, dest)

    # Create config.yaml
    config_path = root / "config.yaml"
    example = Path(__file__).parent.parent / "config.example.yaml"
    if example.exists():
        shutil.copy2(example, config_path)
    else:
        config_path.write_text(
            "editor: vim\n\nprojects:\n  # Add your projects here:\n"
            "  # my_project:\n  #   path: /path/to/project\n"
            "  #   has_git: true\n  #   results_dir: results/\n"
            "  #   logs_dir: logs/\n",
            encoding="utf-8",
        )

    # Init git
    subprocess.run(["git", "init", str(root)], capture_output=True)

    console.print(f"[green]Initialized labbook at {root}[/green]")
    console.print(f"  Edit [cyan]{config_path}[/cyan] to register your projects.")
    console.print(f"  Then run [cyan]lab log <project> \"first entry\"[/cyan] to start.")


# ─── Journal ────────────────────────────────────────────────────────────────


@app.command()
def new(
    project: Annotated[str, typer.Argument(help="Project short name")],
    title: Annotated[str, typer.Argument(help="Entry title")],
    entry_type: Annotated[str, typer.Option("--type", "-t", help="experiment|devlog|decision")] = "devlog",
    tags: Annotated[Optional[list[str]], typer.Option("--tag", "-g", help="Tags")] = None,
    figures: Annotated[Optional[list[Path]], typer.Option("--fig", "-f", help="Figures to archive")] = None,
    code_refs: Annotated[Optional[list[str]], typer.Option("--code", "-c", help="Code file references")] = None,
    edit: Annotated[bool, typer.Option("--edit/--no-edit", help="Open in editor")] = True,
    commit: Annotated[bool, typer.Option("--commit/--no-commit", help="Auto-commit")] = True,
):
    """Create a new journal entry."""
    _validate_project(project)
    if entry_type not in VALID_TYPES:
        console.print(f"[red]Invalid type '{entry_type}'. Use: {', '.join(VALID_TYPES)}[/red]")
        raise typer.Exit(1)

    config = load_config()
    tags = tags or []
    code_refs = code_refs or []

    # Archive figures if provided
    archived_figs = []
    for fig_path in (figures or []):
        rel = archive_figure(fig_path, config, project)
        archived_figs.append(rel)

    # Create entry with template body
    template = _load_template(entry_type)
    entry = Entry(
        date=_today(),
        project=project,
        title=title,
        entry_type=entry_type,
        tags=tags,
        body=template,
        figures=archived_figs,
        code_refs=code_refs,
    )

    path = save_entry(config, entry)
    console.print(f"[green]Created:[/green] {path.relative_to(config.root)}")

    # Open in editor
    if edit:
        _open_in_editor(path)
        # Reload after editing (user may have changed the body)
        entry = load_entry(path)

    # Auto-commit
    if commit:
        files_to_commit = [path]
        for fig_rel in archived_figs:
            files_to_commit.append(config.figures_dir / fig_rel)
        msg = f"lab: {project} - {title} ({entry.date.isoformat()})"
        commit_entry(config, files_to_commit, msg)


@app.command()
def log(
    project: Annotated[str, typer.Argument(help="Project short name")],
    message: Annotated[str, typer.Argument(help="Quick log message")],
    tags: Annotated[Optional[list[str]], typer.Option("--tag", "-g", help="Tags")] = None,
    commit: Annotated[bool, typer.Option("--commit/--no-commit", help="Auto-commit")] = True,
):
    """Quick one-line log entry (no editor, immediate commit)."""
    _validate_project(project)
    config = load_config()

    entry = Entry(
        date=_today(),
        project=project,
        title=message,
        entry_type="devlog",
        tags=tags or [],
        body=f"## Summary\n\n{message}\n",
    )

    path = save_entry(config, entry)
    console.print(f"[green]Logged:[/green] {path.relative_to(config.root)}")

    if commit:
        msg = f"lab: {project} - {message} ({entry.date.isoformat()})"
        commit_entry(config, [path], msg)


@app.command("list")
def list_cmd(
    project: Annotated[Optional[str], typer.Option("--project", "-p", help="Filter by project")] = None,
    entry_type: Annotated[Optional[str], typer.Option("--type", "-t", help="Filter by type")] = None,
    tag: Annotated[Optional[str], typer.Option("--tag", "-g", help="Filter by tag")] = None,
    last: Annotated[int, typer.Option("--last", "-n", help="Show last N entries")] = 20,
    after: Annotated[Optional[str], typer.Option("--after", help="After date (YYYY-MM-DD)")] = None,
    before: Annotated[Optional[str], typer.Option("--before", help="Before date (YYYY-MM-DD)")] = None,
):
    """List journal entries with optional filters."""
    config = load_config()

    after_date = datetime.date.fromisoformat(after) if after else None
    before_date = datetime.date.fromisoformat(before) if before else None
    tags = [tag] if tag else None

    results = search_entries(
        config,
        project=project,
        entry_type=entry_type,
        tags=tags,
        after=after_date,
        before=before_date,
    )

    print_entry_list(results[:last])


@app.command()
def show(
    entry_id: Annotated[str, typer.Argument(help="Entry filename or partial match")],
):
    """Display a full entry in the terminal."""
    config = load_config()
    paths = list_entries(config)

    # Find matching entry
    matches = [p for p in paths if entry_id in p.name]
    if not matches:
        console.print(f"[red]No entry matching '{entry_id}'[/red]")
        raise typer.Exit(1)
    if len(matches) > 1:
        console.print(f"[yellow]Multiple matches ({len(matches)}), showing first:[/yellow]")

    path = matches[0]
    entry = load_entry(path)
    print_entry_detail(entry, path)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search text")],
    project: Annotated[Optional[str], typer.Option("--project", "-p", help="Filter by project")] = None,
):
    """Full-text search across entries."""
    config = load_config()
    results = search_entries(config, query=query, project=project)

    if not results:
        console.print(f"[dim]No results for '{query}'[/dim]")
        return

    console.print(f"[bold]Found {len(results)} entries matching '{query}':[/bold]")
    print_entry_list(results)


@app.command()
def archive(
    source: Annotated[Path, typer.Argument(help="Figure file to archive")],
    project: Annotated[str, typer.Argument(help="Project short name")],
    description: Annotated[str, typer.Option("--desc", "-d", help="Description for filename")] = "",
    commit: Annotated[bool, typer.Option("--commit/--no-commit", help="Auto-commit")] = True,
):
    """Archive a figure into the labbook."""
    _validate_project(project)
    config = load_config()

    rel = archive_figure(source, config, project, description)

    if commit:
        fig_path = config.figures_dir / rel
        msg = f"lab: {project} - archive {Path(rel).name}"
        commit_entry(config, [fig_path], msg)


@app.command()
def push():
    """Push labbook to remote repository."""
    config = load_config()
    git_push(config)


@app.command()
def status():
    """Show labbook status: entry count, recent entries, git status."""
    config = load_config()

    all_paths = list_entries(config)
    total = len(all_paths)

    recent = []
    for p in all_paths[:5]:
        try:
            entry = load_entry(p)
            recent.append((p, entry))
        except (ValueError, KeyError):
            continue

    projects = list(config.projects.keys())
    print_status(total, recent, projects)

    git_st = get_status(config)
    if git_st:
        console.print(f"\n[bold]Git status:[/bold]\n{git_st}")
    else:
        console.print("\n[dim]Git: clean[/dim]")


# ─── Todo ────────────────────────────────────────────────────────────────────

todo_app = typer.Typer(name="todo", help="Per-project task management.", no_args_is_help=True)
app.add_typer(todo_app)


@todo_app.command("add")
def todo_add(
    project: Annotated[str, typer.Argument(help="Project short name")],
    task: Annotated[str, typer.Argument(help="Task description")],
    tags: Annotated[Optional[list[str]], typer.Option("--tag", "-g", help="Tags")] = None,
    commit: Annotated[bool, typer.Option("--commit/--no-commit")] = True,
):
    """Add a todo item to a project."""
    from .todo import add_todo
    _validate_project(project)
    config = load_config()
    path = add_todo(config, project, task, tags)
    console.print(f"[green]Added:[/green] {task}")
    if commit:
        commit_entry(config, [path], f"lab: {project} - todo: {task}")


@todo_app.command("done")
def todo_done(
    project: Annotated[str, typer.Argument(help="Project short name")],
    index: Annotated[int, typer.Argument(help="Task number (from lab todo list)")],
    commit: Annotated[bool, typer.Option("--commit/--no-commit")] = True,
):
    """Mark a todo item as done."""
    from .todo import done_todo, _todos_path
    _validate_project(project)
    config = load_config()
    if done_todo(config, project, index):
        console.print(f"[green]Done:[/green] #{index}")
        if commit:
            commit_entry(config, [_todos_path(config, project)],
                         f"lab: {project} - done #{index}")
    else:
        console.print(f"[red]Invalid index: {index}[/red]")


@todo_app.command("rm")
def todo_rm(
    project: Annotated[str, typer.Argument(help="Project short name")],
    index: Annotated[int, typer.Argument(help="Task number")],
):
    """Remove a todo item."""
    from .todo import remove_todo
    _validate_project(project)
    config = load_config()
    if remove_todo(config, project, index):
        console.print(f"[green]Removed:[/green] #{index}")
    else:
        console.print(f"[red]Invalid index: {index}[/red]")


@todo_app.command("list")
def todo_list(
    project: Annotated[Optional[str], typer.Option("--project", "-p", help="Filter by project")] = None,
    all_items: Annotated[bool, typer.Option("--all", "-a", help="Include done items")] = False,
):
    """List todo items."""
    from .todo import list_todos
    config = load_config()
    list_todos(config, project, show_done=all_items)


# ─── Pathway ─────────────────────────────────────────────────────────────────


@app.command()
def pathway(
    project: Annotated[Optional[str], typer.Argument(help="Project short name")] = None,
    edit: Annotated[bool, typer.Option("--edit", "-e", help="Open in editor")] = False,
    commit: Annotated[bool, typer.Option("--commit/--no-commit")] = True,
):
    """View or edit a project pathway/roadmap."""
    from .pathway import show_pathway, edit_pathway, list_pathways, pathway_path
    config = load_config()

    if project is None:
        list_pathways(config)
        return

    _validate_project(project)

    if edit:
        path = edit_pathway(config, project)
        if commit:
            commit_entry(config, [path],
                         f"lab: {project} - update pathway")
    else:
        show_pathway(config, project)


# ─── Audit & Clean ───────────────────────────────────────────────────────────


@app.command()
def audit(
    target: Annotated[Path, typer.Argument(help="Directory to audit")],
    detail: Annotated[bool, typer.Option("--detail", "-d", help="Show full paths")] = False,
):
    """Audit directory structure: sizes, redundancy, junk files."""
    from .audit import audit_directory
    audit_directory(target, detail=detail)


@app.command()
def clean(
    target: Annotated[Path, typer.Argument(help="Directory to clean")],
    execute: Annotated[bool, typer.Option("--execute", help="Actually delete (default: dry-run)")] = False,
):
    """Find and remove cache files, __pycache__, hidden junk, empty dirs."""
    from .audit import find_junk, print_junk, execute_clean
    junk = find_junk(target)
    total = print_junk(junk, target)

    if total == 0:
        return

    if not execute:
        console.print("\n[dim]Dry run. Use --execute to actually delete.[/dim]")
        return

    confirm = typer.confirm(f"\nDelete {total} items?")
    if confirm:
        removed = execute_clean(junk)
        console.print(f"[green]Removed {removed} items.[/green]")


# ─── Report ──────────────────────────────────────────────────────────────────


@app.command()
def report(
    date: Annotated[Optional[str], typer.Option("--date", "-d", help="Date (YYYY-MM-DD)")] = None,
    days: Annotated[int, typer.Option("--days", "-n", help="Cover last N days")] = 1,
    commit: Annotated[bool, typer.Option("--commit/--no-commit")] = True,
):
    """Generate a daily work report with cross-project references."""
    from .report import show_report, save_report, generate_report
    config = load_config()
    d = datetime.date.fromisoformat(date) if date else datetime.date.today()
    show_report(config, d, days)

    if commit:
        content = generate_report(config, d, days)
        path = save_report(config, content, d)
        commit_entry(config, [path], f"lab: daily report ({d.isoformat()})")


# ─── Scan ────────────────────────────────────────────────────────────────────


@app.command()
def scan(
    project: Annotated[Optional[str], typer.Option("--project", "-p", help="Scan one project")] = None,
    since: Annotated[Optional[int], typer.Option("--since", "-s", help="Look back N hours")] = None,
    save: Annotated[bool, typer.Option("--save/--no-save", help="Auto-create journal entries")] = True,
    commit: Annotated[bool, typer.Option("--commit/--no-commit")] = True,
):
    """Auto-scan project directories for new commits, results, and logs."""
    from .scan import scan_all, print_scan_results, create_scan_entries

    config = load_config()
    if project:
        _validate_project(project)

    activities = scan_all(config, project=project, since_hours=since)
    print_scan_results(activities)

    if save and activities:
        create_scan_entries(config, activities, auto_commit=commit)


# ─── Stats ──────────────────────────────────────────────────────────────────


@app.command()
def stats():
    """Show labbook statistics dashboard: entries, tags, streaks, weekly activity."""
    from .stats import compute_stats, render_stats
    config = load_config()
    render_stats(console, compute_stats(config))


# ─── Weekly ─────────────────────────────────────────────────────────────────


@app.command()
def weekly(
    week_offset: Annotated[int, typer.Option("--week", "-w", help="Week offset (0=current, -1=last)")] = 0,
    edit: Annotated[bool, typer.Option("--edit/--no-edit", help="Open in editor after generating")] = False,
    commit: Annotated[bool, typer.Option("--commit/--no-commit")] = True,
):
    """Generate weekly report for advisor meetings."""
    from .weekly import week_range, generate_weekly, save_weekly, show_weekly
    config = load_config()
    monday, sunday = week_range(week_offset)
    show_weekly(config, monday, sunday)
    content = generate_weekly(config, monday, sunday)
    path = save_weekly(config, content, monday)
    console.print(f"\n[dim]Saved: {path.relative_to(config.root)}[/dim]")
    if edit:
        _open_in_editor(path)
    if commit:
        commit_entry(config, [path], f"lab: weekly report ({monday.isoformat()})")


# ─── Reproduce ──────────────────────────────────────────────────────────────

reproduce_app = typer.Typer(name="reproduce", help="Reproducibility snapshots.", no_args_is_help=True)
app.add_typer(reproduce_app)


@reproduce_app.command("capture")
def reproduce_capture(
    project: Annotated[str, typer.Argument(help="Project short name")],
    run_command: Annotated[Optional[str], typer.Option("--cmd", "-c", help="Run command to record")] = None,
    commit: Annotated[bool, typer.Option("--commit/--no-commit")] = True,
):
    """Capture reproducibility snapshot of current environment."""
    from .reproduce import capture_snapshot, save_snapshot, render_snapshot
    _validate_project(project)
    config = load_config()
    snapshot = capture_snapshot(config, project, run_command)
    render_snapshot(console, snapshot)
    path = save_snapshot(config, snapshot)
    console.print(f"[green]Saved:[/green] {path.relative_to(config.root)}")
    if commit:
        commit_entry(config, [path], f"lab: {project} - reproduce snapshot")


@reproduce_app.command("show")
def reproduce_show(
    query: Annotated[str, typer.Argument(help="Entry filename, project name, or .reproduce.yaml path")],
):
    """Display reproducibility info for an entry or snapshot."""
    from .reproduce import find_snapshot, load_snapshot, render_snapshot
    config = load_config()
    path = find_snapshot(config, query)
    if not path:
        console.print(f"[red]No reproduce snapshot found for '{query}'[/red]")
        raise typer.Exit(1)
    snapshot = load_snapshot(path)
    render_snapshot(console, snapshot)
    console.print(f"[dim]File: {path}[/dim]")


@reproduce_app.command("run")
def reproduce_run(
    query: Annotated[str, typer.Argument(help="Entry filename, project name, or .reproduce.yaml path")],
):
    """Print commands to recreate the environment from a snapshot."""
    from .reproduce import find_snapshot, load_snapshot, format_reproduce_commands
    config = load_config()
    path = find_snapshot(config, query)
    if not path:
        console.print(f"[red]No reproduce snapshot found for '{query}'[/red]")
        raise typer.Exit(1)
    snapshot = load_snapshot(path)
    console.print(format_reproduce_commands(snapshot))
