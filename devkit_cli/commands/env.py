"""devkit env — List, export, diff, and set environment variables."""

import os
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict."""
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


@click.group()
def env():
    """Manage and inspect environment variables."""
    pass


@env.command("list")
@click.option("--filter", "filter_str", default=None, metavar="KEYWORD",
              help="Only show vars containing this keyword (case-insensitive).")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def env_list(filter_str, as_json):
    """
    List all current environment variables.

    \b
    Examples:
      devkit env list
      devkit env list --filter PATH
      devkit env list --json
    """
    vars_dict = dict(os.environ)

    if filter_str:
        keyword = filter_str.lower()
        vars_dict = {k: v for k, v in vars_dict.items()
                     if keyword in k.lower() or keyword in v.lower()}

    if as_json:
        click.echo(json.dumps(vars_dict, indent=2))
        return

    table = Table(title=f"Environment Variables ({len(vars_dict)})")
    table.add_column("Variable", style="cyan", no_wrap=True)
    table.add_column("Value", style="green", overflow="fold")

    for key in sorted(vars_dict):
        table.add_row(key, vars_dict[key])

    console.print(table)


@env.command("export")
@click.argument("output", default=".env", metavar="OUTPUT_FILE")
@click.option("--filter", "filter_str", default=None, metavar="KEYWORD",
              help="Only export vars containing this keyword.")
@click.option("--format", "fmt",
              type=click.Choice(["dotenv", "json", "shell", "powershell", "cmd"]),
              default="dotenv", show_default=True,
              help="Output format. 'shell'=bash export, 'powershell'=$env: syntax, 'cmd'=set syntax.")
def env_export(output, filter_str, fmt):
    """
    Export environment variables to a file.

    \b
    Examples:
      devkit env export                         # exports all to .env
      devkit env export prod.env --filter AWS
      devkit env export vars.json --format json
      devkit env export vars.ps1  --format powershell   # Windows PowerShell
      devkit env export vars.bat  --format cmd          # Windows CMD
    """
    vars_dict = dict(os.environ)
    if filter_str:
        keyword = filter_str.lower()
        vars_dict = {k: v for k, v in vars_dict.items()
                     if keyword in k.lower()}

    out = Path(output)

    if fmt == "dotenv":
        lines = [f'{k}="{v}"' for k, v in sorted(vars_dict.items())]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif fmt == "json":
        out.write_text(json.dumps(vars_dict, indent=2), encoding="utf-8")
    elif fmt == "shell":
        lines = [f"export {k}={json.dumps(v)}" for k, v in sorted(vars_dict.items())]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif fmt == "powershell":
        lines = [f'$env:{k} = {json.dumps(v)}' for k, v in sorted(vars_dict.items())]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif fmt == "cmd":
        # Values with special CMD characters are quoted; newlines replaced with space
        lines = [f"set {k}={v.replace(chr(10), ' ')}" for k, v in sorted(vars_dict.items())]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    console.print(f"[green]✔[/green] Exported [bold]{len(vars_dict)}[/bold] variables to [cyan]{out}[/cyan]")


@env.command("diff")
@click.argument("file_a", type=click.Path(exists=True))
@click.argument("file_b", type=click.Path(exists=True))
def env_diff(file_a, file_b):
    """
    Diff two .env files and show what changed.

    \b
    Example:
      devkit env diff .env .env.production
    """
    a = _load_dotenv(Path(file_a))
    b = _load_dotenv(Path(file_b))

    all_keys = sorted(set(a) | set(b))

    table = Table(title=f"Diff: {file_a}  →  {file_b}")
    table.add_column("Key", style="cyan")
    table.add_column(Path(file_a).name, style="dim")
    table.add_column(Path(file_b).name, style="bold")
    table.add_column("Status", style="bold")

    changed = 0
    for key in all_keys:
        va = a.get(key)
        vb = b.get(key)
        if va == vb:
            continue
        if va is None:
            status = "[green]+added[/green]"
        elif vb is None:
            status = "[red]-removed[/red]"
        else:
            status = "[yellow]~changed[/yellow]"
        table.add_row(key, va or "—", vb or "—", status)
        changed += 1

    if changed == 0:
        console.print("[green]✔[/green] Files are identical.")
    else:
        console.print(table)
        console.print(f"[dim]{changed} difference(s)[/dim]")
