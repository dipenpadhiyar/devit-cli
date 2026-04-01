"""devkit info — Display system, Python, and environment information."""

import os
import platform
import shutil
import sys
from pathlib import Path

import click
import psutil
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns

console = Console()


def _bytes_to_human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _detect_env() -> tuple[str, str]:
    """Return (env_type, env_path)."""
    conda = os.environ.get("CONDA_DEFAULT_ENV")
    if conda:
        return "conda", conda
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        return "venv", venv
    return "none", "—"


@click.command()
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def info(as_json):
    """
    Show system info: OS, Python, CPU, memory, disk, and active environment.

    \b
    Examples:
      devkit info
      devkit info --json
    """
    # --- Gather data ---
    uname = platform.uname()
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(Path.cwd().anchor)
    cpu_count = psutil.cpu_count(logical=True)
    cpu_phys = psutil.cpu_count(logical=False)
    cpu_freq = psutil.cpu_freq()
    env_type, env_path = _detect_env()

    data = {
        "os": f"{uname.system} {uname.release}",
        "machine": uname.machine,
        "hostname": uname.node,
        "python_version": sys.version.split()[0],
        "python_impl": platform.python_implementation(),
        "python_path": sys.executable,
        "cpu_logical": cpu_count,
        "cpu_physical": cpu_phys,
        "cpu_freq_mhz": f"{cpu_freq.current:.0f} MHz" if cpu_freq else "n/a",
        "mem_total": _bytes_to_human(vm.total),
        "mem_used": _bytes_to_human(vm.used),
        "mem_pct": f"{vm.percent}%",
        "disk_total": _bytes_to_human(disk.total),
        "disk_used": _bytes_to_human(disk.used),
        "disk_pct": f"{disk.percent}%",
        "env_type": env_type,
        "env_path": env_path,
        "cwd": str(Path.cwd()),
    }

    if as_json:
        import json
        click.echo(json.dumps(data, indent=2))
        return

    # --- Rich tables ---
    def kv_table(title: str, rows: list[tuple[str, str]]) -> Table:
        t = Table(title=title, show_header=False, box=None, padding=(0, 2))
        t.add_column("Key", style="dim", no_wrap=True)
        t.add_column("Value", style="bold")
        for k, v in rows:
            t.add_row(k, v)
        return t

    sys_table = kv_table("System", [
        ("OS", data["os"]),
        ("Arch", data["machine"]),
        ("Hostname", data["hostname"]),
        ("CWD", data["cwd"]),
    ])

    py_table = kv_table("Python", [
        ("Version", data["python_version"]),
        ("Impl", data["python_impl"]),
        ("Executable", data["python_path"]),
        ("Env Type", data["env_type"]),
        ("Env Path", data["env_path"]),
    ])

    hw_table = kv_table("Hardware", [
        ("CPU (logical)", str(data["cpu_logical"])),
        ("CPU (physical)", str(data["cpu_physical"])),
        ("CPU Freq", data["cpu_freq_mhz"]),
        ("RAM Total", data["mem_total"]),
        ("RAM Used", f"{data['mem_used']} ({data['mem_pct']})"),
        ("Disk Total", data["disk_total"]),
        ("Disk Used", f"{data['disk_used']} ({data['disk_pct']})"),
    ])

    console.print(Panel("[bold cyan]devkit info[/bold cyan]", expand=False))
    console.print(Columns([sys_table, py_table, hw_table], equal=False, expand=False))
