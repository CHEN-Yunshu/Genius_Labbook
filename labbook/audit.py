"""Directory audit and cleanup — find redundancy, junk files, structure issues."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()

# Files/dirs to always skip when walking
SKIP_DIRS = {".git"}

# Junk patterns
HIDDEN_EXCLUDE = {".git", ".gitignore", ".gitmodules", ".gitattributes", ".env"}
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
              ".cache", ".tox", "node_modules", ".eggs", "*.egg-info"}
CACHE_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}
CACHE_EXTENSIONS = {".pyc", ".pyo", ".pyd", ".swp", ".swo", "~"}


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


def _is_hidden(name: str) -> bool:
    return name.startswith(".") and name not in HIDDEN_EXCLUDE


def _is_cache_dir(name: str) -> bool:
    return name in CACHE_DIRS or name.endswith(".egg-info")


def _is_cache_file(path: Path) -> bool:
    name = path.name
    if name in CACHE_FILES:
        return True
    if path.suffix in CACHE_EXTENSIONS:
        return True
    if name.endswith("~"):
        return True
    return False


# ─── Audit ───────────────────────────────────────────────────────────────────


def audit_directory(target: Path, max_depth: int = 3, detail: bool = False) -> dict:
    """Audit a directory: structure, sizes, potential issues.

    Returns a summary dict.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        console.print(f"[red]Not a directory: {target}[/red]")
        return {}

    stats = {
        "total_files": 0,
        "total_size": 0,
        "dir_count": 0,
        "empty_dirs": [],
        "large_files": [],     # > 100MB
        "hidden_files": [],
        "cache_dirs": [],
        "cache_files": [],
        "duplicate_names": defaultdict(list),
        "extensions": defaultdict(int),
        "top_dirs": [],        # biggest subdirectories
    }

    # First pass: collect top-level dir sizes
    dir_sizes = {}
    for item in sorted(target.iterdir()):
        if item.name in SKIP_DIRS:
            continue
        if item.is_dir():
            size = _dir_size(item)
            dir_sizes[item.name] = size

    stats["top_dirs"] = sorted(dir_sizes.items(), key=lambda x: x[1], reverse=True)

    # Full walk
    for root, dirs, files in os.walk(target):
        root_path = Path(root)
        rel = root_path.relative_to(target)
        depth = len(rel.parts)

        # Skip .git internals
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        stats["dir_count"] += 1

        # Check empty dir
        if not files and not dirs:
            stats["empty_dirs"].append(str(rel))

        # Check cache dirs
        for d in list(dirs):
            if _is_cache_dir(d):
                full = root_path / d
                size = _dir_size(full)
                stats["cache_dirs"].append((str(rel / d), size))
                dirs.remove(d)  # Don't descend

        # Check hidden dirs
        for d in list(dirs):
            if _is_hidden(d):
                stats["hidden_files"].append(str(rel / d) + "/")

        for f in files:
            fpath = root_path / f
            stats["total_files"] += 1

            try:
                fsize = fpath.stat().st_size
            except OSError:
                continue

            stats["total_size"] += fsize
            stats["extensions"][fpath.suffix.lower()] += 1

            # Duplicate names
            stats["duplicate_names"][f].append(str(rel / f))

            # Large files
            if fsize > 100 * 1024 * 1024:
                stats["large_files"].append((str(rel / f), fsize))

            # Hidden files
            if _is_hidden(f):
                stats["hidden_files"].append(str(rel / f))

            # Cache files
            if _is_cache_file(fpath):
                stats["cache_files"].append((str(rel / f), fsize))

    # Filter duplicates to only those with >1 occurrence
    stats["duplicate_names"] = {
        k: v for k, v in stats["duplicate_names"].items() if len(v) > 1
    }

    _print_audit(target, stats, detail)
    return stats


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except PermissionError:
        pass
    return total


def _print_audit(target: Path, stats: dict, detail: bool) -> None:
    console.print(f"\n[bold]Audit: {target}[/bold]\n")

    # Overview
    console.print(f"  Files: [cyan]{stats['total_files']:,}[/cyan]")
    console.print(f"  Dirs:  [cyan]{stats['dir_count']:,}[/cyan]")
    console.print(f"  Size:  [cyan]{_human_size(stats['total_size'])}[/cyan]")

    # Top dirs by size
    if stats["top_dirs"]:
        console.print(f"\n[bold]Top directories by size:[/bold]")
        table = Table(show_lines=False)
        table.add_column("Directory", style="green")
        table.add_column("Size", style="cyan", justify="right")
        for name, size in stats["top_dirs"][:10]:
            table.add_row(name, _human_size(size))
        console.print(table)

    # Issues
    issues = 0

    if stats["cache_dirs"]:
        issues += len(stats["cache_dirs"])
        total_cache = sum(s for _, s in stats["cache_dirs"])
        console.print(f"\n[yellow]Cache directories ({len(stats['cache_dirs'])})[/yellow] — {_human_size(total_cache)}")
        if detail:
            for path, size in stats["cache_dirs"][:20]:
                console.print(f"  {path}  ({_human_size(size)})")

    if stats["cache_files"]:
        issues += len(stats["cache_files"])
        total_cache = sum(s for _, s in stats["cache_files"])
        console.print(f"[yellow]Cache/temp files ({len(stats['cache_files'])})[/yellow] — {_human_size(total_cache)}")
        if detail:
            for path, size in stats["cache_files"][:20]:
                console.print(f"  {path}  ({_human_size(size)})")

    if stats["hidden_files"]:
        issues += len(stats["hidden_files"])
        console.print(f"[yellow]Hidden files/dirs ({len(stats['hidden_files'])})[/yellow]")
        if detail:
            for path in stats["hidden_files"][:20]:
                console.print(f"  {path}")

    if stats["empty_dirs"]:
        issues += len(stats["empty_dirs"])
        console.print(f"[yellow]Empty directories ({len(stats['empty_dirs'])})[/yellow]")
        if detail:
            for path in stats["empty_dirs"][:20]:
                console.print(f"  {path}/")

    if stats["large_files"]:
        console.print(f"\n[bold]Large files (>100MB):[/bold]")
        for path, size in sorted(stats["large_files"], key=lambda x: x[1], reverse=True)[:10]:
            console.print(f"  {path}  ({_human_size(size)})")

    dups = stats["duplicate_names"]
    if dups:
        console.print(f"\n[yellow]Duplicate filenames ({len(dups)}):[/yellow]")
        if detail:
            for name, paths in list(dups.items())[:15]:
                console.print(f"  [bold]{name}[/bold] x{len(paths)}")
                for p in paths[:5]:
                    console.print(f"    {p}")

    if issues == 0:
        console.print("\n[green]No issues found.[/green]")
    else:
        console.print(f"\n[bold]Total issues: {issues}[/bold]")
        console.print("[dim]Use --detail for full paths. Use 'lab clean' to remove junk.[/dim]")


# ─── Clean ───────────────────────────────────────────────────────────────────


def find_junk(target: Path) -> dict:
    """Find all cleanable junk in a directory."""
    target = Path(target).resolve()
    junk = {
        "cache_dirs": [],     # (__pycache__, .pytest_cache, etc.)
        "cache_files": [],    # (.DS_Store, *.pyc, etc.)
        "hidden": [],         # .* files (excluding .git, .gitignore)
        "empty_dirs": [],
    }

    for root, dirs, files in os.walk(target):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for d in list(dirs):
            full = root_path / d
            if _is_cache_dir(d):
                size = _dir_size(full)
                junk["cache_dirs"].append((full, size))
                dirs.remove(d)
            elif _is_hidden(d):
                size = _dir_size(full)
                junk["hidden"].append((full, size))

        if not files and not dirs:
            junk["empty_dirs"].append(root_path)

        for f in files:
            fpath = root_path / f
            try:
                fsize = fpath.stat().st_size
            except OSError:
                continue
            if _is_cache_file(fpath):
                junk["cache_files"].append((fpath, fsize))
            elif _is_hidden(f):
                junk["hidden"].append((fpath, fsize))

    return junk


def print_junk(junk: dict, target: Path) -> int:
    """Print junk summary. Returns total count."""
    total = 0
    total_size = 0

    for category, label in [
        ("cache_dirs", "Cache directories"),
        ("cache_files", "Cache/temp files"),
        ("hidden", "Hidden files/dirs"),
        ("empty_dirs", "Empty directories"),
    ]:
        items = junk[category]
        if not items:
            continue

        if category == "empty_dirs":
            console.print(f"\n[yellow]{label} ({len(items)}):[/yellow]")
            for p in items[:30]:
                console.print(f"  {p.relative_to(target)}/")
            total += len(items)
        else:
            cat_size = sum(s for _, s in items)
            total_size += cat_size
            console.print(f"\n[yellow]{label} ({len(items)}) — {_human_size(cat_size)}:[/yellow]")
            for p, s in items[:30]:
                console.print(f"  {p.relative_to(target)}  ({_human_size(s)})")
            total += len(items)

    if total == 0:
        console.print("[green]No junk found.[/green]")
    else:
        console.print(f"\n[bold]Total: {total} items, {_human_size(total_size)} reclaimable[/bold]")

    return total


def execute_clean(junk: dict) -> int:
    """Actually delete junk files. Returns count of items removed."""
    import shutil
    removed = 0

    for p, _ in junk.get("cache_dirs", []):
        try:
            shutil.rmtree(p)
            removed += 1
        except OSError:
            console.print(f"[red]Failed to remove: {p}[/red]")

    for p, _ in junk.get("cache_files", []):
        try:
            p.unlink()
            removed += 1
        except OSError:
            console.print(f"[red]Failed to remove: {p}[/red]")

    for p, _ in junk.get("hidden", []):
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            removed += 1
        except OSError:
            console.print(f"[red]Failed to remove: {p}[/red]")

    for p in junk.get("empty_dirs", []):
        try:
            p.rmdir()
            removed += 1
        except OSError:
            pass  # May no longer be empty after other removals

    return removed
