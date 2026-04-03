"""devkit init — Interactive project scaffold wizard."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import click
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

PROJECT_TYPES = {
    "package": "Python Package  (pip-installable library with pyproject.toml)",
    "fastapi": "FastAPI Backend  (REST API server with async support)",
    "django": "Django Project  (full-stack web framework)",
    "aws":     "AWS Scripts      (Boto3 scripts, Lambda, CDK automation)",
}

ENV_TYPES = {
    "venv":  "Native venv  (built-in, no extra tools needed)",
    "conda": "Conda        (Anaconda/Miniconda environment)",
    "none":  "Skip         (set up manually later)",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path | None = None, capture: bool = False):
    """Run a subprocess; raises CalledProcessError on failure."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        capture_output=capture,
        text=True,
    )


def _create_venv(project_dir: Path, python_version: str) -> None:
    """Create a native venv inside project_dir."""
    with Progress(SpinnerColumn(), TextColumn("[bold green]Creating venv..."), transient=True) as p:
        p.add_task("")
        try:
            _run([sys.executable, "-m", "venv", ".venv"], cwd=project_dir)
        except subprocess.CalledProcessError as e:
            console.print(f"[red]✗[/red] Failed to create virtual environment.\n  [dim]{e}[/dim]")
            raise click.Abort()
    console.print("[green]✔[/green] Virtual environment created at [cyan].venv/[/cyan]")


def _create_conda_env(project_dir: Path, name: str, python_version: str) -> None:
    """Create a conda environment."""
    conda_bin = shutil.which("conda")
    if not conda_bin:
        console.print("[yellow]⚠[/yellow]  conda not found on PATH — skipping env creation.")
        return
    with Progress(SpinnerColumn(), TextColumn(f"[bold green]Creating conda env '{name}'..."), transient=True) as p:
        p.add_task("")
        try:
            _run([conda_bin, "create", "-n", name, f"python={python_version}", "-y"])
        except subprocess.CalledProcessError as e:
            console.print(f"[red]✗[/red] Failed to create conda environment.\n  [dim]{e}[/dim]")
            raise click.Abort()
    console.print(f"[green]✔[/green] Conda environment [cyan]{name}[/cyan] created.")


def _list_conda_envs() -> list[tuple[str, str]]:
    """Return [(name, path), ...] for every conda environment found."""
    conda_bin = shutil.which("conda")
    if not conda_bin:
        return []
    try:
        result = subprocess.run(
            [conda_bin, "env", "list", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout)
        envs = []
        for env_path in data.get("envs", []):
            p = Path(env_path)
            envs.append((p.name, env_path))
        return envs
    except Exception:
        return []


def _list_system_pythons() -> list[tuple[str, str]]:
    """Return [(label, executable_path), ...] for Python installs on this machine."""
    import platform
    seen: dict[str, str] = {}  # exe_path -> label

    def _add(exe: str, label: str) -> None:
        key = str(Path(exe).resolve())
        if key not in seen:
            seen[key] = label

    # Current interpreter — always first
    _add(sys.executable, f"Python {platform.python_version()} — current  ({sys.executable})")

    # Windows Python Launcher: py -0 lists every registered version
    if sys.platform == "win32" and shutil.which("py"):
        try:
            r = subprocess.run(["py", "-0"], capture_output=True, text=True, timeout=5)
            for line in (r.stdout + r.stderr).splitlines():
                m = re.match(r"\s*-(\d+\.\d+)[-\w]*", line)
                if m:
                    ver = m.group(1)
                    try:
                        path = subprocess.run(
                            ["py", f"-{ver}", "-c", "import sys; print(sys.executable)"],
                            capture_output=True, text=True, timeout=5,
                        ).stdout.strip()
                        if path:
                            _add(path, f"Python {ver}  ({path})")
                    except Exception:
                        pass
        except Exception:
            pass

    # python / python3 on PATH
    for alias in ("python", "python3"):
        exe = shutil.which(alias)
        if exe:
            try:
                ver_out = subprocess.run(
                    [exe, "-c", "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}')"],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip()
                _add(exe, f"Python {ver_out}  ({exe})")
            except Exception:
                pass

    # Linux / macOS: scan versioned executables in common locations
    if sys.platform != "win32":
        import glob
        scan_patterns = [
            "/usr/bin/python3.*",
            "/usr/local/bin/python3.*",
            "/opt/homebrew/bin/python3.*",          # macOS Homebrew (Apple Silicon)
            "/usr/local/opt/python*/bin/python3.*", # macOS Homebrew (Intel)
            os.path.expanduser("~/.pyenv/versions/*/bin/python"),  # pyenv
            "/root/.pyenv/versions/*/bin/python",
        ]
        for pattern in scan_patterns:
            for exe in sorted(glob.glob(pattern)):
                if os.path.isfile(exe) and os.access(exe, os.X_OK):
                    try:
                        ver_out = subprocess.run(
                            [exe, "-c", "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}')"],
                            capture_output=True, text=True, timeout=5,
                        ).stdout.strip()
                        if ver_out:
                            _add(exe, f"Python {ver_out}  ({exe})")
                    except Exception:
                        pass

    # Return as list; current interpreter is always at index 0
    result = []
    cur = str(Path(sys.executable).resolve())
    for path, label in seen.items():
        if path == cur:
            result.insert(0, (label, path))
        else:
            result.append((label, path))
    return result


def _ask_env() -> dict:
    """Interactive two-step env prompt — type then create-vs-use-existing.

    Returns an env-decision dict with keys:
        kind          : 'venv_new' | 'venv_existing' | 'conda_new' | 'conda_existing' | 'none'
        python_path   : str | None   (venv_existing)
        conda_name    : str | None   (conda_existing)
        label         : str          (human-readable summary for the project table)
    """
    env_type = questionary.select(
        "Python environment:",
        choices=[questionary.Choice(title=desc, value=key) for key, desc in ENV_TYPES.items()],
    ).ask()
    if env_type is None:
        raise click.Abort()

    if env_type == "none":
        return {"kind": "none", "python_path": None, "conda_name": None, "label": "None (skip)"}

    # ── venv ──────────────────────────────────────────────────────────────
    if env_type == "venv":
        action = questionary.select(
            "venv setup:",
            choices=[
                questionary.Choice("Create new .venv  (recommended)", value="new"),
                questionary.Choice("Use an existing Python interpreter on this machine", value="existing"),
            ],
        ).ask()
        if action is None:
            raise click.Abort()

        if action == "new":
            return {"kind": "venv_new", "python_path": None, "conda_name": None, "label": "New .venv"}

        pythons = _list_system_pythons()
        if not pythons:
            console.print("[yellow]⚠[/yellow]  No Python installations detected — creating default venv.")
            return {"kind": "venv_new", "python_path": None, "conda_name": None, "label": "New .venv"}

        choice = questionary.select(
            "Select Python interpreter:",
            choices=[questionary.Choice(title=label, value=path) for label, path in pythons],
        ).ask()
        if choice is None:
            raise click.Abort()
        # Build a tidy label from the selected entry
        short = next((lbl.split("—")[0].strip() for lbl, p in pythons if p == choice), choice)
        return {"kind": "venv_existing", "python_path": choice, "conda_name": None, "label": f".venv  ({short})"}

    # ── conda ─────────────────────────────────────────────────────────────
    if env_type == "conda":
        action = questionary.select(
            "Conda setup:",
            choices=[
                questionary.Choice("Create new conda environment", value="new"),
                questionary.Choice("Use an existing conda environment", value="existing"),
            ],
        ).ask()
        if action is None:
            raise click.Abort()

        if action == "new":
            return {"kind": "conda_new", "python_path": None, "conda_name": None, "label": "New conda env"}

        envs = _list_conda_envs()
        if not envs:
            console.print("[yellow]⚠[/yellow]  No conda environments found — will create a new one.")
            return {"kind": "conda_new", "python_path": None, "conda_name": None, "label": "New conda env"}

        choice = questionary.select(
            "Select conda environment:",
            choices=[
                questionary.Choice(title=f"{name}  ({path})", value=name)
                for name, path in envs
            ],
        ).ask()
        if choice is None:
            raise click.Abort()
        return {"kind": "conda_existing", "python_path": None, "conda_name": choice, "label": f"conda: {choice}"}

    return {"kind": "none", "python_path": None, "conda_name": None, "label": "None (skip)"}


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_template(template_name: str, dest: Path, context: dict) -> None:
    """Copy a template folder to dest, substituting {{key}} placeholders in
    both file contents AND in file/directory names."""
    template_root = Path(__file__).parent.parent / "templates" / template_name
    if not template_root.exists():
        console.print(f"[red]Template '{template_name}' not found.[/red]")
        return

    def _resolve_name(name: str) -> str:
        for key, val in context.items():
            name = name.replace("{{" + key + "}}", val)
        return name

    for src in template_root.rglob("*"):
        rel = src.relative_to(template_root)
        # Substitute placeholders in every path component (dir and file names)
        resolved_parts = [_resolve_name(part) for part in rel.parts]
        dst = dest / Path(*resolved_parts)
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            try:
                text = src.read_text(encoding="utf-8")
                for key, val in context.items():
                    text = text.replace("{{" + key + "}}", val)
                _write_file(dst, text)
            except (UnicodeDecodeError, ValueError):
                # Binary file (e.g. .pyc, images) — copy as-is
                import shutil as _shutil
                dst.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# Project-type scaffold functions
# ---------------------------------------------------------------------------

def _scaffold_package(project_dir: Path, ctx: dict) -> None:
    name = ctx["project_name"]
    module = name.replace("-", "_")
    ctx["module_name"] = module

    _copy_template("package", project_dir, ctx)

    # Extra dirs
    for d in ["tests", "docs"]:
        (project_dir / d).mkdir(exist_ok=True)
        (project_dir / d / ".gitkeep").touch()

    console.print("[green]✔[/green] Python package scaffold created.")


def _scaffold_fastapi(project_dir: Path, ctx: dict) -> None:
    _copy_template("fastapi", project_dir, ctx)
    console.print("[green]✔[/green] FastAPI project scaffold created.")


def _scaffold_django(project_dir: Path, ctx: dict) -> None:
    _copy_template("django", project_dir, ctx)
    console.print("[green]✔[/green] Django project scaffold created.")


def _scaffold_aws(project_dir: Path, ctx: dict) -> None:
    _copy_template("aws", project_dir, ctx)
    console.print("[green]✔[/green] AWS scripts scaffold created.")


SCAFFOLD_FN = {
    "package": _scaffold_package,
    "fastapi":  _scaffold_fastapi,
    "django":   _scaffold_django,
    "aws":      _scaffold_aws,
}


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@click.command()
@click.argument("project_name", required=False)
@click.option("--type", "project_type", type=click.Choice(list(PROJECT_TYPES)), default=None,
              help="Project type (skip interactive prompt).")
@click.option("--env", "env_type", type=click.Choice(list(ENV_TYPES)), default=None,
              help="Environment type (skip interactive prompt).")
@click.option("--python", "python_version", default="3.11", show_default=True,
              help="Python version for the environment.")
@click.option("--dir", "target_dir", default=None,
              help="Parent directory for the new project (default: current directory).")
@click.option("--yes", "-y", "yes", is_flag=True, default=False,
              help="Skip confirmation prompt.")
def init(project_name, project_type, env_type, python_version, target_dir, yes):
    """
    Scaffold a new project with best-practice structure.

    \b
    Interactive wizard — just run `devkit init` with no arguments.
    Or be explicit:  devkit init my-app --type fastapi --env venv
    """
    console.print(Panel("[bold cyan]devkit init[/bold cyan] — New Project Wizard", expand=False))

    # --- collect info interactively if not supplied via flags ---
    if not project_name:
        project_name = questionary.text(
            "Project name:",
            validate=lambda v: len(v.strip()) > 0 or "Name cannot be empty",
        ).ask()
        if not project_name:
            raise click.Abort()
        project_name = project_name.strip()

    if not project_type:
        project_type = questionary.select(
            "What type of project?",
            choices=[questionary.Choice(title=desc, value=key) for key, desc in PROJECT_TYPES.items()],
        ).ask()
        if not project_type:
            raise click.Abort()

    if env_type:
        # --env flag supplied — map directly, skip sub-prompts
        _kind_map = {"venv": "venv_new", "conda": "conda_new", "none": "none"}
        env_decision: dict = {
            "kind": _kind_map[env_type],
            "python_path": None,
            "conda_name": None,
            "label": ENV_TYPES[env_type].split("(")[0].strip(),
        }
    else:
        env_decision = _ask_env()

    # --- confirm ---
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[dim]Name[/dim]",        f"[bold]{project_name}[/bold]")
    table.add_row("[dim]Type[/dim]",        f"[cyan]{PROJECT_TYPES[project_type].split('(')[0].strip()}[/cyan]")
    table.add_row("[dim]Environment[/dim]", f"[cyan]{env_decision['label']}[/cyan]")
    table.add_row("[dim]Python[/dim]",      python_version)
    console.print(Panel(table, title="[bold]Project Summary[/bold]", expand=False))

    if not yes:
        ok = questionary.confirm("Create project?", default=True).ask()
        if not ok:
            console.print("[yellow]Aborted.[/yellow]")
            raise click.Abort()

    # --- create directory ---
    base = Path(target_dir) if target_dir else Path.cwd()
    project_dir = base / project_name

    if project_dir.exists():
        overwrite = questionary.confirm(
            f"[yellow]'{project_dir}' already exists. Continue anyway?[/yellow]", default=False
        ).ask()
        if not overwrite:
            raise click.Abort()
    else:
        try:
            project_dir.mkdir(parents=True)
        except PermissionError:
            console.print(f"[red]✗[/red] Permission denied: cannot create [cyan]{project_dir}[/cyan]")
            raise click.Abort()

    # --- scaffold ---
    ctx = {
        "project_name": project_name,
        "python_version": python_version,
        "module_name": project_name.replace("-", "_"),
    }
    SCAFFOLD_FN[project_type](project_dir, ctx)

    # --- environment ---
    kind = env_decision["kind"]
    if kind == "venv_new":
        _create_venv(project_dir, python_version)
    elif kind == "venv_existing":
        py_path = env_decision["python_path"]
        with Progress(SpinnerColumn(), TextColumn("[bold green]Creating .venv..."), transient=True) as p:
            p.add_task("")
            try:
                _run([py_path, "-m", "venv", ".venv"], cwd=project_dir)
            except subprocess.CalledProcessError as e:
                console.print(f"[red]✗[/red] Failed to create virtual environment.\n  [dim]{e}[/dim]")
                raise click.Abort()
        console.print("[green]✔[/green] Virtual environment created at [cyan].venv/[/cyan]")
    elif kind == "conda_new":
        _create_conda_env(project_dir, project_name, python_version)
    elif kind == "conda_existing":
        cname = env_decision["conda_name"]
        (project_dir / ".devkit").write_text(f"conda_env={cname}\n", encoding="utf-8")
        console.print(f"[green]✔[/green] Linked to conda env [cyan]{cname}[/cyan].")
        console.print(f"  [dim]Activate with:[/dim]  [bold]conda activate {cname}[/bold]")

    # --- git init ---
    if shutil.which("git"):
        try:
            _run(["git", "init"], cwd=project_dir, capture=True)
            console.print("[green]✔[/green] Git repository initialised.")
        except Exception:
            console.print("[yellow]⚠[/yellow]  git init failed — skipping.")

    # --- done ---
    console.print()
    console.print(Panel(
        f"[bold green]Project ready![/bold green]\n\n"
        f"  [dim]cd[/dim] [cyan]{project_name}[/cyan]\n"
        f"  [dim]Then run[/dim]  [bold]devkit dev[/bold]  [dim]to start developing.[/dim]",
        expand=False,
    ))
