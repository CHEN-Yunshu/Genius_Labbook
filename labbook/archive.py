"""Figure archival: copy and standardize naming."""

from __future__ import annotations

import datetime
import re
import shutil
from pathlib import Path

from rich.console import Console

from .config import LabbookConfig

console = Console()

MAX_SIZE_MB = 5
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".pdf"}


def _slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s).strip("-")
    return s[:40]


def archive_figure(
    source: Path,
    config: LabbookConfig,
    project: str,
    description: str = "",
    date: datetime.date | None = None,
) -> str:
    """Copy a figure into figures/YYYY/MM/ with standardized name.

    Returns the relative path from figures/ (for embedding in entry frontmatter).
    """
    source = Path(source).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    ext = source.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        console.print(
            f"[yellow]Warning: {ext} is not a standard figure format "
            f"({', '.join(ALLOWED_EXTENSIONS)})[/yellow]"
        )

    size_mb = source.stat().st_size / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        console.print(
            f"[yellow]Warning: file is {size_mb:.1f}MB "
            f"(recommend <{MAX_SIZE_MB}MB for git tracking)[/yellow]"
        )

    if date is None:
        date = datetime.date.today()

    # Build target path
    target_dir = config.figures_dir / str(date.year) / f"{date.month:02d}"
    target_dir.mkdir(parents=True, exist_ok=True)

    desc_slug = _slugify(description) if description else source.stem
    target_name = f"{date.isoformat()}_{project}_{desc_slug}{ext}"
    target = target_dir / target_name

    # Handle duplicates
    if target.exists():
        stem = target.stem
        suffix = 2
        while target.exists():
            target = target_dir / f"{stem}_{suffix}{ext}"
            suffix += 1

    shutil.copy2(source, target)

    # Return relative path from figures/
    rel = target.relative_to(config.figures_dir)
    console.print(f"[green]Archived:[/green] {rel}")
    return str(rel)
