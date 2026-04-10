"""Per-project todo list management, stored as YAML."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from .config import LabbookConfig

console = Console()


@dataclass
class TodoItem:
    task: str
    status: str = "pending"  # pending | done
    added: str = ""
    done_date: str = ""
    tags: list[str] = field(default_factory=list)


def _todos_dir(config: LabbookConfig) -> Path:
    d = config.root / "todos"
    d.mkdir(exist_ok=True)
    return d


def _todos_path(config: LabbookConfig, project: str) -> Path:
    return _todos_dir(config) / f"{project}.yaml"


def _load_todos(config: LabbookConfig, project: str) -> list[dict]:
    path = _todos_path(config, project)
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    return data or []


def _save_todos(config: LabbookConfig, project: str, todos: list[dict]) -> Path:
    path = _todos_path(config, project)
    with open(path, "w") as f:
        yaml.dump(todos, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return path


def add_todo(
    config: LabbookConfig, project: str, task: str, tags: list[str] | None = None
) -> Path:
    todos = _load_todos(config, project)
    todos.append({
        "task": task,
        "status": "pending",
        "added": datetime.date.today().isoformat(),
        "tags": tags or [],
    })
    return _save_todos(config, project, todos)


def done_todo(config: LabbookConfig, project: str, index: int) -> bool:
    todos = _load_todos(config, project)
    if index < 1 or index > len(todos):
        return False
    todos[index - 1]["status"] = "done"
    todos[index - 1]["done_date"] = datetime.date.today().isoformat()
    _save_todos(config, project, todos)
    return True


def remove_todo(config: LabbookConfig, project: str, index: int) -> bool:
    todos = _load_todos(config, project)
    if index < 1 or index > len(todos):
        return False
    todos.pop(index - 1)
    _save_todos(config, project, todos)
    return True


def list_todos(config: LabbookConfig, project: str | None = None, show_done: bool = False) -> None:
    """Print todo lists. If project is None, show all projects."""
    projects = [project] if project else list(config.projects.keys())

    for proj in projects:
        todos = _load_todos(config, proj)
        if not todos:
            continue

        items = todos if show_done else [t for t in todos if t.get("status") != "done"]
        if not items:
            continue

        table = Table(title=f"[bold]{proj}[/bold]", show_lines=False)
        table.add_column("#", style="dim", width=4)
        table.add_column("Status", width=6)
        table.add_column("Task", style="white")
        table.add_column("Tags", style="dim")
        table.add_column("Added", style="cyan", width=10)

        for i, t in enumerate(todos, 1):
            if not show_done and t.get("status") == "done":
                continue
            status_icon = "[green]done[/green]" if t.get("status") == "done" else "[yellow]todo[/yellow]"
            tags = ", ".join(t.get("tags", []))
            table.add_row(str(i), status_icon, t["task"], tags, t.get("added", ""))

        console.print(table)
        console.print()
