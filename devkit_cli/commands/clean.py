"""devkit clean — Remove build artifacts, caches, and junk files."""

import shutil
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()

# Directories to delete entirely
CLEAN_DIRS = [
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "*.egg-info",
    ".eggs",
    "node_modules",
    ".next",
    ".nuxt",
    "htmlcov",
    "site",
    ".tox",
    ".nox",
]

# Individual file patterns to delete
CLEAN_FILES = [
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".DS_Store",
    "Thumbs.db",
    "*.log",
    "*.tmp",
    "*.bak",
    "*.swp",
    "*.swo",
    ".coverage",
    "coverage.xml",
    "*.orig",
]


def _iter_matches(root: Path, patterns: list[str]):
    for pat in patterns:
        yield from root.rglob(pat)


@click.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be removed without deleting.")
@click.option("-y", "--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option("--include-venv", is_flag=True, default=False, help="Also remove .venv/ directory.")
def clean(path, dry_run, yes, include_venv):
    """
    Remove __pycache__, build artifacts, .DS_Store, and other junk.

    \b
    Examples:
      devkit clean               # clean current directory
      devkit clean ./my-project  # clean a specific directory
      devkit clean --dry-run     # preview only
    """
    root = Path(path).resolve()
    to_remove: list[Path] = []

    dir_patterns = list(CLEAN_DIRS)
    if include_venv:
        dir_patterns.append(".venv")

    for item in _iter_matches(root, dir_patterns):
        if item.is_dir():
            to_remove.append(item)

    for item in _iter_matches(root, CLEAN_FILES):
        if item.is_file():
            to_remove.append(item)

    # De-duplicate: skip children of already-queued dirs
    to_remove_set = sorted(set(to_remove), key=lambda p: len(p.parts))
    final: list[Path] = []
    queued_dirs: list[Path] = []
    for item in to_remove_set:
        if any(item.is_relative_to(d) for d in queued_dirs):
            continue
        final.append(item)
        if item.is_dir():
            queued_dirs.append(item)

    if not final:
        console.print("[green]✔[/green] Nothing to clean.")
        return

    table = Table(title=f"Items to remove ({len(final)})", show_lines=False)
    table.add_column("Type", style="dim", width=5)
    table.add_column("Path", style="cyan")

    for item in final:
        kind = "[blue]DIR[/blue]" if item.is_dir() else "FILE"
        table.add_row(kind, str(item.relative_to(root)))

    console.print(table)

    if dry_run:
        console.print("[yellow]Dry-run mode — nothing was deleted.[/yellow]")
        return

    if not yes:
        click.confirm(f"Delete {len(final)} item(s)?", abort=True)

    removed_count = 0
    errors = 0
    for item in final:
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed_count += 1
        except Exception as exc:
            console.print(f"[red]Error removing {item}: {exc}[/red]")
            errors += 1

    console.print(f"[green]✔[/green] Removed [bold]{removed_count}[/bold] item(s)." +
                  (f" [red]{errors} error(s).[/red]" if errors else ""))
