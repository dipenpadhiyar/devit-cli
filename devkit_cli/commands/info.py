"""devkit info — Display system, Python, and environment information."""

import os
import platform
import shutil
import sys
from pathlib import Path

import click
import psutil
from rich import box as rbox
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

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


def _pct_color(pct: float) -> str:
    return "green" if pct < 50 else "yellow" if pct < 80 else "red"


def _fill(pct: float, width: int = 7) -> str:
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


def _build_hw_panel() -> Panel:
    # Sample CPU — 0.5s blocking interval for accurate reading
    cpu_percs: list[float] = psutil.cpu_percent(percpu=True, interval=0.5)
    cpu_freq = psutil.cpu_freq()
    cpu_phys = psutil.cpu_count(logical=False)
    cpu_logical = psutil.cpu_count(logical=True)
    freq_str = f"{cpu_freq.current:.0f} MHz" if cpu_freq else "n/a"

    # ── CPU header
    cpu_header = Text()
    cpu_header.append(f"  {platform.machine()}", style="bold white")
    cpu_header.append(f"  ·  {cpu_phys}C / {cpu_logical}T  ·  {freq_str}", style="dim")

    # ── Core grid: each core is a rounded-border cell, 4 per row
    cols = min(4, len(cpu_percs))
    core_tbl = Table(
        box=rbox.ROUNDED, show_header=False,
        padding=(0, 1), expand=False, border_style="cyan",
    )
    for _ in range(cols):
        core_tbl.add_column(no_wrap=True, justify="center")

    row: list[Text] = []
    for i, pct in enumerate(cpu_percs):
        c = _pct_color(pct)
        cell = Text(justify="center")
        cell.append(f"Core {i}\n", style="bold dim")
        cell.append(f"{_fill(pct)}\n", style=f"{c} bold")
        cell.append(f"{pct:4.1f}%", style=c)
        row.append(cell)
        if len(row) == cols:
            core_tbl.add_row(*row)
            row = []
    if row:
        while len(row) < cols:
            row.append(Text(""))
        core_tbl.add_row(*row)

    # ── RAM bar
    vm = psutil.virtual_memory()
    rc = _pct_color(vm.percent)
    ram_text = Text()
    ram_text.append("  RAM  ", style="bold")
    ram_text.append(_fill(vm.percent, 30), style=f"{rc} bold")
    ram_text.append(f"  {vm.percent:.0f}%  ", style=f"{rc} bold")
    ram_text.append(f"{_bytes_to_human(vm.used)} / {_bytes_to_human(vm.total)}", style="dim")

    # ── GPU section
    gpu_content: list[Text] = []
    try:
        import GPUtil  # type: ignore
        gpus = GPUtil.getGPUs()
        if gpus:
            for gpu in gpus:
                load = gpu.load * 100
                vp = (gpu.memoryUsed / gpu.memoryTotal * 100) if gpu.memoryTotal else 0
                gc = _pct_color(load)
                vc = _pct_color(vp)
                g = Text()
                g.append(f"  {gpu.name}", style="bold white")
                g.append(f"  ·  {gpu.temperature}°C\n", style="dim")
                g.append("  Load  ", style="bold")
                g.append(_fill(load, 30), style=f"{gc} bold")
                g.append(f"  {load:.0f}%\n", style=f"{gc} bold")
                g.append("  VRAM  ", style="bold")
                g.append(_fill(vp, 30), style=f"{vc} bold")
                g.append(f"  {vp:.0f}%  ", style=f"{vc} bold")
                g.append(f"{gpu.memoryUsed:.0f} / {gpu.memoryTotal:.0f} MB", style="dim")
                gpu_content.append(g)
        else:
            gpu_content.append(Text("  no GPU detected", style="dim"))
    except ImportError:
        gpu_content.append(Text(
            "  GPU  ─  install GPUtil for NVIDIA stats  (pip install GPUtil)",
            style="dim",
        ))

    content = Group(
        Text(),
        cpu_header,
        Text(),
        core_tbl,
        Text(),
        Rule(style="dim"),
        Text(),
        ram_text,
        Text(),
        Rule(title="[dim]GPU[/dim]", style="dim"),
        Text(),
        *gpu_content,
        Text(),
    )

    return Panel(content, title="[bold cyan]⬡  Hardware Monitor[/bold cyan]", border_style="cyan")


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

    # --- Hardware snapshot ---
    console.print()
    console.print(_build_hw_panel())
