"""devit deps — Dependency manager (wraps pip with nice output)."""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import click
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _venv_python(root: Path) -> str:
    """Return the venv python for the project, or sys.executable as fallback."""
    venv = root / ".venv"
    if venv.exists():
        win_py = venv / "Scripts" / "python.exe"
        unix_py = venv / "bin" / "python"
        if win_py.exists():
            return str(win_py)
        if unix_py.exists():
            return str(unix_py)
    return sys.executable


def _pip(py: str, args: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    """Run pip via the given interpreter. Returns CompletedProcess."""
    cmd = [py, "-m", "pip"] + args
    try:
        return subprocess.run(cmd, capture_output=capture, text=True)
    except FileNotFoundError:
        console.print(f"[red]✗[/red] Python interpreter not found: [bold]{py}[/bold]")
        raise SystemExit(1)


def _installed_version(py: str, name: str) -> str | None:
    """Return the installed version of a package, or None if not found."""
    r = _pip(py, ["show", name], capture=True)
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return None


def _bare_name(pkg_spec: str) -> str:
    """Strip any version specifiers/extras from a package spec → bare name."""
    return re.split(r"[=<>!~\[\s]", pkg_spec)[0].strip()


def _detect_req_file(root: Path) -> Path | None:
    req = root / "requirements.txt"
    return req if req.exists() else None


def _req_add(req_file: Path, name: str, version: str) -> None:
    """Add or replace a package pin in requirements.txt."""
    try:
        lines = req_file.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise click.ClickException(f"Cannot read {req_file.name}: {e}")

    pattern = re.compile(r"^" + re.escape(name) + r"([=<>!~\[\s]|$)", re.IGNORECASE)
    new_line = f"{name}=={version}"
    new_lines, updated = [], False
    for line in lines:
        if pattern.match(line.strip()):
            new_lines.append(new_line)
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(new_line)

    try:
        req_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except OSError as e:
        raise click.ClickException(f"Cannot write {req_file.name}: {e}")


def _req_remove(req_file: Path, name: str) -> bool:
    """Remove a package entry from requirements.txt. Returns True if found."""
    try:
        lines = req_file.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise click.ClickException(f"Cannot read {req_file.name}: {e}")

    pattern = re.compile(r"^" + re.escape(name) + r"([=<>!~\[\s]|$)", re.IGNORECASE)
    new_lines = [l for l in lines if not pattern.match(l.strip())]
    if len(new_lines) == len(lines):
        return False

    try:
        req_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except OSError as e:
        raise click.ClickException(f"Cannot write {req_file.name}: {e}")
    return True


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def deps():
    """Manage project dependencies (wraps pip with nice output)."""
    pass


# ---------------------------------------------------------------------------
# devit deps add
# ---------------------------------------------------------------------------

@deps.command("add")
@click.argument("packages", nargs=-1, required=True)
@click.option("--no-save", is_flag=True, default=False,
              help="Install without updating requirements.txt.")
@click.option("--dir", "project_dir", default=None,
              help="Project directory (default: current directory).")
def deps_add(packages, no_save, project_dir):
    """
    Install package(s) and save to requirements.txt.
    Use [bold].[/bold] as the package name to upgrade ALL outdated packages at once.

    \b
    Examples:
      devit deps add requests
      devit deps add "flask>=3.0" sqlalchemy
      devit deps add numpy --no-save
      devit deps add .          # upgrade all outdated packages
    """
    root = Path(project_dir).resolve() if project_dir else Path.cwd()
    py = _venv_python(root)

    # ── special case: "devit deps add ." → upgrade all outdated ──────────
    if list(packages) == ["."]:
        console.print(Panel("[bold cyan]devit deps add .[/bold cyan] — Upgrading all outdated packages", expand=False))

        with Progress(SpinnerColumn(), TextColumn("[dim]Checking for outdated packages...[/dim]"), transient=True) as p:
            p.add_task("")
            r = _pip(py, ["list", "--outdated", "--format=json"], capture=True)

        if r.returncode != 0:
            console.print("[red]✗[/red] Could not check for outdated packages.")
            raise SystemExit(1)

        try:
            outdated = json.loads(r.stdout)
        except json.JSONDecodeError:
            console.print("[red]✗[/red] Failed to parse pip output.")
            raise SystemExit(1)

        if not outdated:
            console.print("[green]✔[/green] All packages are already up to date.")
            return

        table = Table(title=f"Upgrading {len(outdated)} package(s)", show_lines=False)
        table.add_column("Package", style="cyan")
        table.add_column("Current", style="dim")
        table.add_column("→ Latest", style="bold green")
        for pkg in sorted(outdated, key=lambda p: p["name"].lower()):
            table.add_row(pkg["name"], pkg["version"], pkg["latest_version"])
        console.print(table)

        names = [pkg["name"] for pkg in outdated]
        result = _pip(py, ["install", "--upgrade"] + names)
        if result.returncode != 0:
            console.print("[red]✗[/red] Upgrade failed.")
            raise SystemExit(result.returncode)

        if not no_save:
            req_file = _detect_req_file(root)
            if req_file:
                saved = []
                for pkg in outdated:
                    new_ver = _installed_version(py, pkg["name"])
                    if new_ver:
                        try:
                            _req_add(req_file, pkg["name"], new_ver)
                            saved.append(f"{pkg['name']}=={new_ver}")
                        except click.ClickException as e:
                            console.print(f"[yellow]⚠[/yellow]  {e.format_message()}")
                if saved:
                    console.print(
                        f"[green]✔[/green] Updated [cyan]{req_file.name}[/cyan] with "
                        f"[bold]{len(saved)}[/bold] new version(s)."
                    )

        console.print(f"[green]✔[/green] Upgraded [bold]{len(names)}[/bold] package(s) successfully.")
        return
    # ─────────────────────────────────────────────────────────────────────

    console.print(Panel("[bold cyan]devit deps add[/bold cyan]", expand=False))

    # Install via pip (stream output live so user sees progress)
    result = _pip(py, ["install"] + list(packages))
    if result.returncode != 0:
        console.print("[red]✗[/red] Installation failed.")
        raise SystemExit(result.returncode)

    if no_save:
        return

    req_file = _detect_req_file(root)
    if not req_file:
        console.print(
            "[dim]No requirements.txt found in this directory — "
            "packages installed but not saved.[/dim]"
        )
        return

    saved = []
    for pkg in packages:
        name = _bare_name(pkg)
        version = _installed_version(py, name)
        if not version:
            console.print(f"[yellow]⚠[/yellow]  Could not determine version for [bold]{name}[/bold] — skipping save.")
            continue
        try:
            _req_add(req_file, name, version)
            saved.append(f"{name}=={version}")
        except click.ClickException as e:
            console.print(f"[yellow]⚠[/yellow]  {e.format_message()}")

    if saved:
        console.print(
            f"[green]✔[/green] Saved to [cyan]{req_file.name}[/cyan]: "
            + ", ".join(f"[bold]{s}[/bold]" for s in saved)
        )


# ---------------------------------------------------------------------------
# devit deps remove
# ---------------------------------------------------------------------------

@deps.command("remove")
@click.argument("packages", nargs=-1, required=True)
@click.option("--no-save", is_flag=True, default=False,
              help="Uninstall without updating requirements.txt.")
@click.option("--dir", "project_dir", default=None,
              help="Project directory (default: current directory).")
def deps_remove(packages, no_save, project_dir):
    """
    Uninstall package(s) and remove from requirements.txt.

    \b
    Examples:
      devit deps remove requests
      devit deps remove flask sqlalchemy
    """
    root = Path(project_dir).resolve() if project_dir else Path.cwd()
    py = _venv_python(root)

    console.print(Panel("[bold cyan]devit deps remove[/bold cyan]", expand=False))

    result = _pip(py, ["uninstall", "-y"] + list(packages))
    if result.returncode != 0:
        console.print("[red]✗[/red] Uninstall failed.")
        raise SystemExit(result.returncode)

    if no_save:
        return

    req_file = _detect_req_file(root)
    if not req_file:
        return

    removed = []
    for pkg in packages:
        name = _bare_name(pkg)
        try:
            found = _req_remove(req_file, name)
            if found:
                removed.append(name)
        except click.ClickException as e:
            console.print(f"[yellow]⚠[/yellow]  {e.format_message()}")

    if removed:
        console.print(
            f"[green]✔[/green] Removed from [cyan]{req_file.name}[/cyan]: "
            + ", ".join(f"[bold]{n}[/bold]" for n in removed)
        )


# ---------------------------------------------------------------------------
# devit deps list
# ---------------------------------------------------------------------------

@deps.command("list")
@click.option("--dir", "project_dir", default=None,
              help="Project directory (default: current directory).")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def deps_list(project_dir, as_json):
    """
    List all packages installed in the project environment.

    \b
    Examples:
      devit deps list
      devit deps list --json
    """
    root = Path(project_dir).resolve() if project_dir else Path.cwd()
    py = _venv_python(root)

    result = _pip(py, ["list", "--format=json"], capture=True)
    if result.returncode != 0:
        console.print("[red]✗[/red] Could not retrieve package list.")
        raise SystemExit(1)

    try:
        packages = json.loads(result.stdout)
    except json.JSONDecodeError:
        console.print("[red]✗[/red] Failed to parse pip output.")
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(packages, indent=2))
        return

    table = Table(title=f"Installed Packages ({len(packages)})", show_lines=False)
    table.add_column("Package", style="cyan")
    table.add_column("Version", style="bold green")

    for pkg in sorted(packages, key=lambda p: p["name"].lower()):
        table.add_row(pkg["name"], pkg["version"])

    console.print(table)


# ---------------------------------------------------------------------------
# devit deps outdated
# ---------------------------------------------------------------------------

@deps.command("outdated")
@click.option("--dir", "project_dir", default=None,
              help="Project directory (default: current directory).")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def deps_outdated(project_dir, as_json):
    """
    Show packages that have newer versions available.

    \b
    Examples:
      devit deps outdated
      devit deps outdated --json
    """
    root = Path(project_dir).resolve() if project_dir else Path.cwd()
    py = _venv_python(root)

    with Progress(
        SpinnerColumn(),
        TextColumn("[dim]Checking for updates...[/dim]"),
        transient=True,
    ) as p:
        p.add_task("")
        result = _pip(py, ["list", "--outdated", "--format=json"], capture=True)

    if result.returncode != 0:
        console.print("[red]✗[/red] Could not check for updates.")
        raise SystemExit(1)

    try:
        packages = json.loads(result.stdout)
    except json.JSONDecodeError:
        console.print("[red]✗[/red] Failed to parse pip output.")
        raise SystemExit(1)

    if not packages:
        console.print("[green]✔[/green] All packages are up to date.")
        return

    if as_json:
        click.echo(json.dumps(packages, indent=2))
        return

    table = Table(title=f"Outdated Packages ({len(packages)})", show_lines=False)
    table.add_column("Package", style="cyan")
    table.add_column("Installed", style="dim")
    table.add_column("Latest", style="bold green")
    table.add_column("Type", style="dim")

    for pkg in sorted(packages, key=lambda p: p["name"].lower()):
        table.add_row(
            pkg["name"],
            pkg["version"],
            pkg["latest_version"],
            pkg.get("latest_filetype", "wheel"),
        )

    console.print(table)
    console.print(
        f"\n[dim]Run [bold]devit deps add <name>[/bold] to upgrade one  "
        f"or [bold]devit deps add .[/bold] to upgrade all.[/dim]"
    )


# ---------------------------------------------------------------------------
# Snapshot storage helpers
# ---------------------------------------------------------------------------

_SNAPSHOTS_FILE = Path(".devit") / "dep_snapshots.json"


def _snapshots_path(root: Path) -> Path:
    return root / _SNAPSHOTS_FILE


def _load_snapshots(root: Path) -> list[dict]:
    path = _snapshots_path(root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("expected a list")
        return data
    except (json.JSONDecodeError, ValueError):
        console.print(
            f"[yellow]⚠[/yellow]  Snapshot file is corrupted ([dim]{path}[/dim]) — "
            "existing history could not be loaded."
        )
        return []
    except OSError as e:
        console.print(f"[yellow]⚠[/yellow]  Could not read snapshot file: {e}")
        return []


def _save_snapshots(root: Path, snapshots: list[dict]) -> None:
    path = _snapshots_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshots, indent=2), encoding="utf-8")
    except OSError as e:
        raise click.ClickException(f"Cannot save snapshots: {e}")


def _get_current_packages(py: str) -> list[dict]:
    result = _pip(py, ["list", "--format=json"], capture=True)
    if result.returncode != 0:
        console.print("[red]\u2717[/red] Could not retrieve package list.")
        raise SystemExit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        console.print("[red]\u2717[/red] Failed to parse pip output.")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# devit deps snapshot
# ---------------------------------------------------------------------------

@deps.command("snapshot")
@click.option("--message", "-m", default=None,
              help="Label for this snapshot (e.g. 'working baseline').")
@click.option("--dir", "project_dir", default=None,
              help="Project directory (default: current directory).")
def deps_snapshot(message, project_dir):
    """
    Save a snapshot of the current dependency state.

    \b
    Examples:
      devit deps snapshot
      devit deps snapshot -m "working with flask 3.0"
    """
    root = Path(project_dir).resolve() if project_dir else Path.cwd()
    py = _venv_python(root)

    packages = _get_current_packages(py)
    snapshots = _load_snapshots(root)

    snap_id = (max(s["id"] for s in snapshots) + 1) if snapshots else 1
    timestamp = datetime.now().isoformat(timespec="seconds")
    label = message or f"Snapshot #{snap_id}"

    snapshots.append({
        "id": snap_id,
        "message": label,
        "timestamp": timestamp,
        "packages": [{"name": p["name"], "version": p["version"]} for p in packages],
    })
    try:
        _save_snapshots(root, snapshots)
    except click.ClickException as e:
        console.print(f"[red]\u2717[/red] {e.format_message()}")
        raise SystemExit(1)

    console.print(
        f"[green]\u2714[/green] Snapshot [bold]#{snap_id}[/bold] saved — "
        f"[cyan]{label}[/cyan]  [dim]({len(packages)} packages · {timestamp})[/dim]"
    )


# ---------------------------------------------------------------------------
# devit deps history
# ---------------------------------------------------------------------------

@deps.command("history")
@click.option("--dir", "project_dir", default=None,
              help="Project directory (default: current directory).")
def deps_history(project_dir):
    """
    List all saved dependency snapshots.

    \b
    Example:
      devit deps history
    """
    root = Path(project_dir).resolve() if project_dir else Path.cwd()
    snapshots = _load_snapshots(root)

    if not snapshots:
        console.print(
            "[yellow]No snapshots yet.[/yellow]  "
            "Run [bold]devit deps snapshot[/bold] to save one."
        )
        return

    table = Table(title=f"Dependency Snapshots ({len(snapshots)})", show_lines=False)
    table.add_column("ID",       style="dim",        width=5)
    table.add_column("Message",  style="cyan")
    table.add_column("Packages", justify="right",    style="bold green", width=10)
    table.add_column("Saved At", style="dim")

    for s in reversed(snapshots):
        table.add_row(
            f"#{s['id']}",
            s["message"],
            str(len(s["packages"])),
            s["timestamp"],
        )

    console.print(table)
    console.print(
        f"[dim]  devit deps diff <ID>      — compare to current env\n"
        f"  devit deps rollback <ID>  — restore a snapshot[/dim]"
    )


# ---------------------------------------------------------------------------
# devit deps diff
# ---------------------------------------------------------------------------

@deps.command("diff")
@click.argument("snapshot_id", type=int, required=False)
@click.option("--dir", "project_dir", default=None,
              help="Project directory (default: current directory).")
def deps_diff(snapshot_id, project_dir):
    """
    Diff current environment against a snapshot. Shows what changed and flags issues.

    \b
    Examples:
      devit deps diff          # compare to latest snapshot
      devit deps diff 2        # compare to snapshot #2
    """
    root = Path(project_dir).resolve() if project_dir else Path.cwd()
    py = _venv_python(root)
    snapshots = _load_snapshots(root)

    if not snapshots:
        console.print(
            "[yellow]No snapshots found.[/yellow]  "
            "Run [bold]devit deps snapshot[/bold] first."
        )
        return

    if snapshot_id is None:
        snap = snapshots[-1]
    else:
        snap = next((s for s in snapshots if s["id"] == snapshot_id), None)
        if not snap:
            console.print(f"[red]\u2717[/red] Snapshot [bold]#{snapshot_id}[/bold] not found. "
                          f"Run [bold]devit deps history[/bold] to see available IDs.")
            raise SystemExit(1)

    current_pkgs = {p["name"].lower(): p["version"] for p in _get_current_packages(py)}
    snap_pkgs    = {p["name"].lower(): p["version"] for p in snap["packages"]}

    all_names = sorted(set(current_pkgs) | set(snap_pkgs))

    issues: list[str] = []
    rows: list[tuple] = []
    for name in all_names:
        cur = current_pkgs.get(name)
        old = snap_pkgs.get(name)
        if cur == old:
            continue
        if old is None:
            rows.append((name, "\u2014", cur, "[green]+added[/green]"))
        elif cur is None:
            rows.append((name, old, "\u2014", "[red]-removed[/red]"))
            issues.append(f"[bold]{name}[/bold] was removed (snapshot had {old})")
        else:
            rows.append((name, old, cur, "[yellow]~changed[/yellow]"))
            issues.append(f"[bold]{name}[/bold] version changed  {old} \u2192 {cur}")

    if not rows:
        console.print(
            f"[green]\u2714[/green] Environment matches snapshot "
            f"[bold]#{snap['id']}[/bold]  [dim]{snap['message']}[/dim]"
        )
        return

    table = Table(
        title=f"Diff: current  vs  Snapshot #{snap['id']}  \u00b7  {snap['message']}  [{snap['timestamp']}]",
        show_lines=False,
    )
    table.add_column("Package",  style="cyan")
    table.add_column("Snapshot", style="dim")
    table.add_column("Current",  style="bold")
    table.add_column("Status",   style="bold")

    for name, old, cur, status in rows:
        table.add_row(name, old, cur, status)

    console.print(table)

    if issues:
        console.print()
        console.print("[red bold]Issues detected:[/red bold]")
        for issue in issues:
            console.print(f"  [red]\u2022[/red] {issue}")
        console.print()
        console.print(
            f"  [dim]Run [bold]devit deps rollback {snap['id']}[/bold] "
            f"to restore this snapshot.[/dim]"
        )


# ---------------------------------------------------------------------------
# devit deps rollback
# ---------------------------------------------------------------------------

@deps.command("rollback")
@click.argument("snapshot_id", type=int, required=False)
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option("--dir", "project_dir", default=None,
              help="Project directory (default: current directory).")
def deps_rollback(snapshot_id, yes, project_dir):
    """
    Reinstall exact package versions from a saved snapshot.

    \b
    Examples:
      devit deps rollback        # rollback to latest snapshot
      devit deps rollback 2      # rollback to snapshot #2
      devit deps rollback 2 --yes
    """
    root = Path(project_dir).resolve() if project_dir else Path.cwd()
    py = _venv_python(root)
    snapshots = _load_snapshots(root)

    if not snapshots:
        console.print("[yellow]No snapshots found.[/yellow]")
        return

    if snapshot_id is None:
        snap = snapshots[-1]
    else:
        snap = next((s for s in snapshots if s["id"] == snapshot_id), None)
        if not snap:
            console.print(f"[red]\u2717[/red] Snapshot [bold]#{snapshot_id}[/bold] not found. "
                          f"Run [bold]devit deps history[/bold] to see available IDs.")
            raise SystemExit(1)

    # Show what will change before asking
    current_pkgs = {p["name"].lower(): p["version"] for p in _get_current_packages(py)}
    snap_pkgs    = {p["name"].lower(): p["version"] for p in snap["packages"]}

    diffs = [
        (name, current_pkgs.get(name, "\u2014"), ver)
        for name, ver in snap_pkgs.items()
        if current_pkgs.get(name) != ver
    ]

    console.print(
        f"Rolling back to snapshot [bold]#{snap['id']}[/bold] — "
        f"[cyan]{snap['message']}[/cyan]  [dim]{snap['timestamp']}[/dim]"
    )

    if diffs:
        table = Table(title=f"Changes that will be applied ({len(diffs)})", show_lines=False)
        table.add_column("Package",  style="cyan")
        table.add_column("Current",  style="dim")
        table.add_column("\u2192 Restore", style="bold green")
        for name, cur, restore in diffs:
            table.add_row(name, cur, restore)
        console.print(table)
    else:
        console.print("[green]\u2714[/green] Environment already matches this snapshot — nothing to do.")
        return

    if not yes:
        ok = questionary.confirm(
            "Reinstall these exact versions?", default=True
        ).ask()
        if not ok:
            console.print("[yellow]Aborted.[/yellow]")
            raise click.Abort()

    pins = [f"{p['name']}=={p['version']}" for p in snap["packages"]]

    if not pins:
        console.print("[yellow]⚠[/yellow]  Snapshot has no packages — nothing to install.")
        return

    console.print(f"[dim]Installing {len(pins)} pinned package(s)...[/dim]")
    # Run pip OUTSIDE any Progress/spinner so its live output is not garbled
    result = _pip(py, ["install"] + pins)

    if result.returncode != 0:
        console.print("[red]✗[/red] Rollback failed — see errors above.")
        raise SystemExit(result.returncode)

    console.print(
        f"[green]\u2714[/green] Rolled back to snapshot [bold]#{snap['id']}[/bold] successfully.\n"
        f"  [dim]Restored [bold]{len(pins)}[/bold] packages to exact pinned versions.[/dim]"
    )
