"""Configuration loading for labbook."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ProjectConfig:
    name: str
    path: str
    has_git: bool = False
    results_dir: str | None = None
    logs_dir: str | None = None


@dataclass
class LabbookConfig:
    root: Path
    editor: str = "vim"
    projects: dict[str, ProjectConfig] = field(default_factory=dict)

    @property
    def entries_dir(self) -> Path:
        return self.root / "entries"

    @property
    def figures_dir(self) -> Path:
        return self.root / "figures"

    @property
    def templates_dir(self) -> Path:
        return self.root / "templates"


def _find_root() -> Path:
    """Find labbook root by walking up from CWD, then from this file."""
    # 1. Walk up from current working directory
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / "config.yaml").exists():
            return parent

    # 2. Walk up from package install location
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "config.yaml").exists():
        return candidate

    raise FileNotFoundError(
        "Cannot find labbook root (no config.yaml found). "
        "Run 'lab init' to set up a new labbook, or run from inside your labbook directory."
    )


def load_config(root: Path | None = None) -> LabbookConfig:
    """Load configuration from config.yaml."""
    if root is None:
        root = _find_root()
    config_path = root / "config.yaml"
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    projects = {}
    for name, proj in (raw.get("projects") or {}).items():
        projects[name] = ProjectConfig(
            name=name,
            path=proj.get("path", ""),
            has_git=proj.get("has_git", False),
            results_dir=proj.get("results_dir"),
            logs_dir=proj.get("logs_dir"),
        )

    return LabbookConfig(
        root=root,
        editor=raw.get("editor", "vim"),
        projects=projects,
    )
