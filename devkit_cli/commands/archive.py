"""devkit zip / devkit unzip — Archive utilities with progress bars."""

import zipfile
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    FileSizeColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

console = Console()


def _bytes_to_human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# ZIP
# ---------------------------------------------------------------------------

@click.command("zip")
@click.argument("output", metavar="OUTPUT.zip")
@click.argument("sources", nargs=-1, required=True, metavar="FILE_OR_DIR...")
@click.option("-l", "--level", default=6, show_default=True,
              type=click.IntRange(0, 9), help="Compression level (0=none, 9=max).")
@click.option("-x", "--exclude", multiple=True,
              help="Glob pattern(s) to exclude, e.g. -x '*.pyc' -x '__pycache__'")
def zip_cmd(output, sources, level, exclude):
    """
    Create a ZIP archive from files/directories.

    \b
    Examples:
      devkit zip archive.zip src/ README.md
      devkit zip dist.zip . -x __pycache__ -x '*.pyc' -l 9
    """
    out_path = Path(output)
    if not out_path.suffix:
        out_path = out_path.with_suffix(".zip")

    # Collect all files
    all_files: list[tuple[Path, str]] = []
    for src_str in sources:
        src = Path(src_str)
        if not src.exists():
            console.print(f"[red]Source not found: {src}[/red]")
            raise click.Abort()
        if src.is_dir():
            for f in src.rglob("*"):
                if f.is_file():
                    arc_name = str(f.relative_to(src.parent))
                    skip = any(f.match(pat) for pat in exclude)
                    if not skip:
                        all_files.append((f, arc_name))
        else:
            skip = any(src.match(pat) for pat in exclude)
            if not skip:
                all_files.append((src, src.name))

    if not all_files:
        console.print("[yellow]No files to archive.[/yellow]")
        return

    total_size = sum(f.stat().st_size for f, _ in all_files)
    console.print(f"Archiving [bold]{len(all_files)}[/bold] files "
                  f"([cyan]{_bytes_to_human(total_size)}[/cyan]) → [green]{out_path}[/green]")

    compress = zipfile.ZIP_DEFLATED if level > 0 else zipfile.ZIP_STORED

    try:
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            FileSizeColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Compressing", total=total_size)
            with zipfile.ZipFile(out_path, "w", compression=compress, compresslevel=level) as zf:
                for fpath, arc_name in all_files:
                    zf.write(fpath, arc_name)
                    progress.advance(task, fpath.stat().st_size)
    except OSError as e:
        console.print(f"[red]✗[/red] Failed to create archive: {e}")
        raise click.Abort()

    final_size = out_path.stat().st_size
    ratio = (1 - final_size / total_size) * 100 if total_size else 0
    console.print(f"[green]✔[/green] Created [bold]{out_path}[/bold] "
                  f"([cyan]{_bytes_to_human(final_size)}[/cyan], "
                  f"[dim]{ratio:.1f}% compression[/dim])")


# ---------------------------------------------------------------------------
# UNZIP
# ---------------------------------------------------------------------------

@click.command("unzip")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False))
@click.argument("destination", default=".", metavar="DEST_DIR")
@click.option("-l", "--list", "list_only", is_flag=True, default=False,
              help="List contents without extracting.")
def unzip_cmd(archive, destination, list_only):
    """
    Extract a ZIP archive with a progress bar.

    \b
    Examples:
      devkit unzip archive.zip
      devkit unzip archive.zip ./output
      devkit unzip archive.zip --list
    """
    arc_path = Path(archive)

    if not zipfile.is_zipfile(arc_path):
        console.print(f"[red]{archive} is not a valid ZIP file.[/red]")
        raise click.Abort()

    with zipfile.ZipFile(arc_path, "r") as zf:
        members = zf.infolist()

        if list_only:
            from rich.table import Table
            table = Table(title=f"Contents of {arc_path.name}")
            table.add_column("File", style="cyan")
            table.add_column("Size", justify="right", style="green")
            table.add_column("Compressed", justify="right", style="dim")
            for m in members:
                if not m.is_dir():
                    table.add_row(
                        m.filename,
                        _bytes_to_human(m.file_size),
                        _bytes_to_human(m.compress_size),
                    )
            console.print(table)
            return

        dest = Path(destination)
        dest.mkdir(parents=True, exist_ok=True)
        total_size = sum(m.file_size for m in members if not m.is_dir())

        try:
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                FileSizeColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Extracting", total=total_size)
                for member in members:
                    zf.extract(member, dest)
                    if not member.is_dir():
                        progress.advance(task, member.file_size)
        except OSError as e:
            console.print(f"[red]✗[/red] Extraction failed: {e}")
            raise click.Abort()

    console.print(f"[green]✔[/green] Extracted [bold]{len(members)}[/bold] items to [cyan]{dest}[/cyan]")
