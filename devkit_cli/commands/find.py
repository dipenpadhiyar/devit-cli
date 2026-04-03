"""devkit find — Fast file search with filters."""

import os
import stat
import time
from datetime import datetime, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _bytes_to_human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _parse_size(s: str) -> int:
    """Parse size strings like '10kb', '2mb', '500' (bytes)."""
    s = s.strip().lower()
    multipliers = {"kb": 1024, "mb": 1024**2, "gb": 1024**3, "b": 1}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            return int(float(s[: -len(suffix)]) * mult)
    return int(s)


@click.command()
@click.argument("pattern", default="*")
@click.option("-d", "--dir", "search_dir", default=".", show_default=True,
              type=click.Path(exists=True, file_okay=False),
              help="Root directory to search.")
@click.option("-e", "--ext", multiple=True,
              help="Filter by extension(s), e.g. -e py -e js")
@click.option("--min-size", default=None, help="Minimum file size, e.g. 10kb.")
@click.option("--max-size", default=None, help="Maximum file size, e.g. 5mb.")
@click.option("--newer-than", default=None, metavar="DAYS",
              help="Files modified within last N days.")
@click.option("--older-than", default=None, metavar="DAYS",
              help="Files modified more than N days ago.")
@click.option("-l", "--limit", default=100, show_default=True,
              help="Maximum results to display.")
@click.option("--dirs-only", is_flag=True, default=False,
              help="Match directories instead of files.")
def find(pattern, search_dir, ext, min_size, max_size, newer_than, older_than, limit, dirs_only):
    """
    Search for files by name pattern with optional filters.

    \b
    Examples:
      devkit find "*.py"
      devkit find "config" -e toml -e ini
      devkit find "*" --min-size 1mb --newer-than 7
      devkit find --dirs-only "src"
    """
    root = Path(search_dir).resolve()
    try:
        min_bytes = _parse_size(min_size) if min_size else None
    except (ValueError, TypeError):
        console.print(f"[red]✗[/red] Invalid --min-size value: [bold]{min_size}[/bold]  (example: 10kb, 2mb)")
        raise SystemExit(1)
    try:
        max_bytes = _parse_size(max_size) if max_size else None
    except (ValueError, TypeError):
        console.print(f"[red]✗[/red] Invalid --max-size value: [bold]{max_size}[/bold]  (example: 10kb, 2mb)")
        raise SystemExit(1)
    try:
        newer_cutoff = (datetime.now() - timedelta(days=int(newer_than))).timestamp() if newer_than else None
    except (ValueError, TypeError):
        console.print(f"[red]✗[/red] --newer-than must be a whole number of days, got: [bold]{newer_than}[/bold]")
        raise SystemExit(1)
    try:
        older_cutoff = (datetime.now() - timedelta(days=int(older_than))).timestamp() if older_than else None
    except (ValueError, TypeError):
        console.print(f"[red]✗[/red] --older-than must be a whole number of days, got: [bold]{older_than}[/bold]")
        raise SystemExit(1)

    table = Table(title=f"Search: [cyan]{pattern}[/cyan] in [dim]{root}[/dim]",
                  show_lines=False, expand=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Path", style="cyan")
    if not dirs_only:
        table.add_column("Size", justify="right", style="green")
        table.add_column("Modified", style="dim")

    results: list[Path] = []

    for item in root.rglob(pattern):
        if dirs_only and not item.is_dir():
            continue
        if not dirs_only and not item.is_file():
            continue

        if ext and item.suffix.lstrip(".").lower() not in [e.lstrip(".").lower() for e in ext]:
            continue

        try:
            st = item.stat()
        except OSError:
            continue

        if not dirs_only:
            if min_bytes is not None and st.st_size < min_bytes:
                continue
            if max_bytes is not None and st.st_size > max_bytes:
                continue

        mtime = st.st_mtime
        if newer_cutoff and mtime < newer_cutoff:
            continue
        if older_cutoff and mtime > older_cutoff:
            continue

        results.append(item)
        if len(results) >= limit:
            break

    if not results:
        console.print("[yellow]No matches found.[/yellow]")
        return

    for i, item in enumerate(results, 1):
        rel = item.relative_to(root)
        if dirs_only:
            table.add_row(str(i), str(rel))
        else:
            st = item.stat()
            mtime_str = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            table.add_row(str(i), str(rel), _bytes_to_human(st.st_size), mtime_str)

    console.print(table)
    console.print(f"[dim]{len(results)} result(s) — limit {limit}[/dim]")
