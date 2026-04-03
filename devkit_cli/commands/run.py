"""devkit run / build / dev / test — Unified task runner (auto-detects project type)."""

import shutil
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

console = Console()


# ---------------------------------------------------------------------------
# Project-type detection
# ---------------------------------------------------------------------------

def _detect_project_type(root: Path) -> str | None:
    """Return project type key or None if unknown."""
    if (root / "manage.py").exists() and (root / "manage.py").read_text(encoding="utf-8", errors="ignore").find("django") != -1:
        return "django"
    if (root / "manage.py").exists():
        return "django"
    for f in ("main.py", "app.py", "server.py", "api.py"):
        fp = root / f
        if fp.exists() and "fastapi" in fp.read_text(encoding="utf-8", errors="ignore").lower():
            return "fastapi"
    if (root / "template.yaml").exists() or (root / "template.yml").exists():
        return "aws"
    if (root / "cdk.json").exists() or (root / "serverless.yml").exists():
        return "aws"
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists() or (root / "setup.cfg").exists():
        return "package"
    return None


def _venv_python(root: Path) -> str:
    """Return path to venv python if .venv exists, else sys.executable."""
    venv = root / ".venv"
    if venv.exists():
        win_py = venv / "Scripts" / "python.exe"
        unix_py = venv / "bin" / "python"
        if win_py.exists():
            return str(win_py)
        if unix_py.exists():
            return str(unix_py)
    return sys.executable


def _is_module_installed(py: str, module: str) -> bool:
    """Check if a Python module is importable in the given interpreter."""
    result = subprocess.run(
        [py, "-c", f"import {module}"],
        capture_output=True,
    )
    return result.returncode == 0


# Key module that must be present before run/dev can work, per project type
_SENTINEL_MODULE = {
    "fastapi": "httpx",     # httpx needed for TestClient; implies fastapi+uvicorn installed too
    "django":  "django",
    "aws":     "boto3",
    "package": None,
}


def _ensure_deps(project_type: str, py: str, root: Path) -> None:
    """Auto-install dependencies if the sentinel module is missing."""
    sentinel = _SENTINEL_MODULE.get(project_type)
    if not sentinel:
        return
    if _is_module_installed(py, sentinel):
        return

    console.print(
        f"[yellow]⚠[/yellow]  [bold]{sentinel}[/bold] not found in this environment — "
        f"installing dependencies first...\n"
    )

    # Pick the right install command based on what exists in the project
    pip = [py, "-m", "pip"]
    if (root / "requirements.txt").exists():
        install_cmd = pip + ["install", "-r", "requirements.txt"]
    elif (root / "pyproject.toml").exists():
        install_cmd = pip + ["install", "-e", ".[dev]"]
    else:
        console.print("[red]No requirements.txt or pyproject.toml found — cannot auto-install.[/red]")
        raise SystemExit(1)

    _run_cmd(install_cmd, root)
    console.print()


def _run_cmd(cmd: list[str], cwd: Path) -> None:
    """Run a command in subprocess, streaming output live."""
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    # Pre-check: is the executable reachable?
    exe = cmd[0]
    if not (shutil.which(exe) or Path(exe).is_file()):
        console.print(
            f"[red]Command not found:[/red] [bold]{exe}[/bold]\n"
            f"  Make sure [cyan]{exe}[/cyan] is installed and on your PATH."
        )
        raise SystemExit(1)
    try:
        result = subprocess.run(cmd, cwd=cwd)
    except FileNotFoundError:
        console.print(
            f"[red]Command not found:[/red] [bold]{cmd[0]}[/bold]\n"
            f"  Make sure [cyan]{cmd[0]}[/cyan] is installed and on your PATH."
        )
        raise SystemExit(1)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


# ---------------------------------------------------------------------------
# Per-project-type handlers
# ---------------------------------------------------------------------------

def _get_handlers(project_type: str, root: Path, py: str) -> dict[str, list[str] | None]:
    django_manage = [py, "manage.py"]
    sam = "sam"

    # Always use "python -m <tool>" — works regardless of whether the tool
    # binary is on PATH, as long as the package is installed in the active env.
    pip     = [py, "-m", "pip"]
    pytest  = [py, "-m", "pytest"]
    uvicorn = [py, "-m", "uvicorn"]
    build   = [py, "-m", "build"]

    # Detect entry-point for fastapi (main:app, app:app, etc.)
    app_module = "main:app"
    for candidate in ("main.py", "app.py", "server.py", "api.py"):
        if (root / candidate).exists():
            app_module = f"{Path(candidate).stem}:app"
            break

    if project_type == "fastapi":
        return {
            "dev":   uvicorn + [app_module, "--reload", "--host", "127.0.0.1", "--port", "8000"],
            "run":   uvicorn + [app_module, "--host", "0.0.0.0", "--port", "8000"],
            "build": pip + ["install", "-r", "requirements.txt"],
            "test":  pytest + ["tests/", "-v"],
        }
    elif project_type == "django":
        return {
            "dev":   django_manage + ["runserver", "127.0.0.1:8000"],
            "run":   django_manage + ["runserver", "0.0.0.0:8000"],
            "build": pip + ["install", "-r", "requirements.txt"],
            "test":  django_manage + ["test"],
        }
    elif project_type == "package":
        return {
            "dev":   pip + ["install", "-e", ".[dev]"],
            "run":   [py, "-m", root.name.replace("-", "_")],
            "build": build,
            "test":  pytest + ["-v"],
        }
    elif project_type == "aws":
        has_sam = (root / "template.yaml").exists() or (root / "template.yml").exists()
        return {
            "dev":   [sam, "local", "start-api"] if has_sam else [py, "-m", "scripts.main"],
            "run":   [py, "-m", "scripts.main"],
            "build": [sam, "build"] if has_sam else pip + ["install", "-r", "requirements.txt"],
            "test":  pytest + ["tests/", "-v"],
        }
    return {
        "dev":   [py, "-m", "main"],
        "run":   [py, "-m", "main"],
        "build": pip + ["install", "-r", "requirements.txt"],
        "test":  pytest + ["-v"],
    }


# ---------------------------------------------------------------------------
# Shared task runner
# ---------------------------------------------------------------------------

def _run_task(task: str, extra_args: tuple, project_dir: str | None) -> None:
    root = Path(project_dir).resolve() if project_dir else Path.cwd()
    project_type = _detect_project_type(root)

    if project_type:
        console.print(f"[dim]Detected project type:[/dim] [bold cyan]{project_type}[/bold cyan]")
    else:
        console.print("[yellow]⚠[/yellow]  Could not auto-detect project type — using generic runner.")
        project_type = "generic"

    py = _venv_python(root)

    # Auto-install deps before run/dev/test if the key package is missing
    if task in ("run", "dev", "test"):
        _ensure_deps(project_type, py, root)

    handlers = _get_handlers(project_type, root, py)
    cmd = handlers.get(task)

    if cmd is None:
        console.print(f"[red]'{task}' is not supported for {project_type} projects.[/red]")
        raise SystemExit(1)

    full_cmd = cmd + list(extra_args)
    console.print(Panel(f"[bold]{task.upper()}[/bold] — [cyan]{project_type}[/cyan]", expand=False))
    _run_cmd(full_cmd, root)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.command()
@click.argument("extra_args", nargs=-1)
@click.option("--dir", "project_dir", default=None, help="Project root (default: cwd).")
def run(extra_args, project_dir):
    """Run the project (production mode)."""
    _run_task("run", extra_args, project_dir)


@click.command()
@click.argument("extra_args", nargs=-1)
@click.option("--dir", "project_dir", default=None, help="Project root (default: cwd).")
def build(extra_args, project_dir):
    """Build / install the project and its dependencies."""
    _run_task("build", extra_args, project_dir)


@click.command()
@click.argument("extra_args", nargs=-1)
@click.option("--dir", "project_dir", default=None, help="Project root (default: cwd).")
def dev(extra_args, project_dir):
    """Start the project in development / watch mode."""
    _run_task("dev", extra_args, project_dir)


@click.command()
@click.argument("extra_args", nargs=-1)
@click.option("--dir", "project_dir", default=None, help="Project root (default: cwd).")
def test(extra_args, project_dir):
    """Run the test suite."""
    _run_task("test", extra_args, project_dir)
