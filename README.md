# Genius Labbook

A git-backed CLI journal for computational research. Track experiments, results, figures, and decisions across multiple projects — without leaving the terminal.

```
$ lab log my_project "Phase1 complete, 8 models x 136 datasets"
Logged: entries/2026/04/2026-04-10_my_project_phase1-complete.md
Committed: a1b2c3d lab: my_project - Phase1 complete (2026-04-10)
```

## Why

- Experiment results scatter across dozens of directories
- You forget what you ran last week and why
- Figures get overwritten, logs get lost, decisions go undocumented

Genius Labbook gives you one place to see everything — plain Markdown + YAML, version-controlled with git.

## Install

```bash
git clone https://github.com/CHEN-Yunshu/Genius_Labbook.git
cd Genius_Labbook
pip install -e .
```

## Quick Start

```bash
# 1. Initialize a labbook
lab init

# 2. Edit config.yaml to register your projects
#    (opens automatically after init)

# 3. Start recording
lab log my_project "trained ResNet50, val_acc=0.94"
lab new my_project "Ablation study" --type experiment --tag ablation
```

## Commands

### Journal

```bash
lab new <project> <title>          # Detailed entry (opens editor)
lab log <project> <message>        # Quick one-liner
lab list                           # Recent entries
lab list -p my_project -t experiment  # Filter by project/type
lab show <entry>                   # Display full entry
lab search "focal loss"            # Full-text search
lab archive fig.png my_project     # Archive a figure
```

### Todo

```bash
lab todo add my_project "Run ablation"  # Add task
lab todo list                           # All pending
lab todo done my_project 1              # Mark done
lab todo rm my_project 2                # Remove
```

### Scan

Auto-detect new git commits, result files, and logs across your projects:

```bash
lab scan                           # All projects, since last scan
lab scan --since 24                # Look back 24 hours
lab scan -p my_project             # One project only
```

### Report

```bash
lab report                         # Today's daily report
lab report --days 7                # Weekly summary
```

### Pathway

```bash
lab pathway my_project             # View project roadmap
lab pathway my_project --edit      # Edit roadmap
```

### Audit & Clean

```bash
lab audit /path/to/project         # Find junk, large files, duplicates
lab clean /path/to/project         # Preview cleanup
lab clean /path/to/project --execute  # Delete junk
```

### Sync

```bash
lab push                           # Push labbook to GitHub
```

## Entry Format

Plain Markdown with YAML frontmatter:

```markdown
---
date: 2026-04-10
project: my_project
type: experiment
tags: [ablation, resnet]
title: Ablation study on backbone architectures
---

## Objective

Compare ResNet50 vs ConvNeXt on our dataset.

## Results

| Backbone  | Val Acc | Train Time |
|-----------|---------|------------|
| ResNet50  | 0.94    | 2.5h       |
| ConvNeXt  | 0.96    | 4.1h       |
```

Entry types: `experiment`, `devlog`, `decision`, `design` — each has a structured template.

## Use with Claude Code

Add this to your Claude Code settings to use `lab` as a skill:

**`.claude/settings.json`**:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "lab",
        "command": "lab scan --no-save --no-commit"
      }
    ]
  }
}
```

Or register your labbook as a custom slash command. Create **`.claude/commands/lab.md`**:
```markdown
You have access to the `lab` CLI for research journaling. Use it to:
- Record experiment results: `lab log <project> "<summary>"`
- Create detailed entries: `lab new <project> "<title>" --type experiment --no-edit`
- Check recent work: `lab list --last 5`
- Search past experiments: `lab search "<query>"`
- Scan for new results: `lab scan`
- View project roadmap: `lab pathway <project>`

Always log significant experiments, decisions, and results.
```

## Directory Structure

```
your-labbook/
├── config.yaml          # Project registry
├── entries/             # Journal entries (by year/month)
├── figures/             # Archived figures
├── todos/               # Per-project task lists
├── pathways/            # Project roadmaps
├── reports/             # Generated reports
└── templates/           # Entry templates
```

## Dependencies

- Python >= 3.10
- [Typer](https://typer.tiangolo.com/) — CLI framework
- [Rich](https://rich.readthedocs.io/) — Terminal formatting
- [PyYAML](https://pyyaml.org/) — Config and data parsing

## License

MIT
