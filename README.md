<p align="center">
  <img src="https://raw.githubusercontent.com/dipenpadhiyar/devit-cli/main/assets/devit.png" alt="devit-cli" width="300"/>
</p>

<p align="center">
  <b>A full-featured CLI toolkit for professional Python developers.</b><br/>
  Scaffold projects &nbsp;·&nbsp; Clean builds &nbsp;·&nbsp; Inspect system &nbsp;·&nbsp; Search files &nbsp;·&nbsp; Manage archives &amp; env vars
</p>

<p align="center">
  <a href="https://pypi.org/project/devit-cli/"><img src="https://img.shields.io/pypi/v/devit-cli.svg" alt="PyPI version"/></a>
  <a href="https://pypistats.org/packages/devit-cli"><img src="https://img.shields.io/pypi/dm/devit-cli.svg?label=PyPI%20downloads" alt="Monthly downloads"/></a>
  <a href="https://pypi.org/project/devit-cli/"><img src="https://img.shields.io/pypi/pyversions/devit-cli.svg" alt="Python versions"/></a>
  <a href="https://pypi.org/project/devit-cli/"><img src="https://img.shields.io/pypi/l/devit-cli.svg" alt="License"/></a>
</p>


---

## Installation

```bash
pip install devit-cli
```

Requires **Python 3.10+**. Works on **Windows · Linux · macOS**.

---

## Quick Start

```bash
devit           # show help + logo
devit init      # interactive project wizard
devit info      # system snapshot
devit clean     # remove caches & build artifacts
devit dev       # start dev server / install in dev mode
devit test      # run tests (auto-detects pytest / django)
```

---

## Commands

### `devit init` — Project wizard

Interactively scaffold a new project. Asks for:

| Question | Options |
|---|---|
| Project type | Python Package · FastAPI · Django · AWS Scripts |
| Environment  | New venv · Existing Python interpreter · New conda · Existing conda env · Skip |
| Python version | e.g. `3.11` |

```bash
devit init                          # fully interactive
devit init my-api --type fastapi --env venv
devit init my-lib --type package --env conda --python 3.12
devit init my-app -y                # skip confirmation prompt
```

#### Generated structures

**Python Package**
```
my-lib/
├── my_lib/
│   ├── __init__.py
│   └── core.py
├── tests/
│   └── test_core.py
├── docs/
├── pyproject.toml
├── README.md
└── .gitignore
```

**FastAPI**
```
my-api/
├── main.py
├── app/
│   └── routers/
│       └── health.py
├── tests/
│   └── test_api.py
├── requirements.txt
├── README.md
└── .gitignore
```

**Django**
```
my-site/
├── manage.py
├── my_site/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   └── core/
│       ├── views.py
│       └── urls.py
├── requirements.txt
└── .gitignore
```

**AWS Scripts**
```
my-aws/
├── scripts/
│   ├── main.py
│   ├── s3.py
│   └── ec2.py
├── tests/
├── requirements.txt
└── .gitignore
```

---

### `devit dev / run / build / test` — Unified task runner

Auto-detects project type and runs the right command:

| Command | Package | FastAPI | Django | AWS |
|---|---|---|---|---|
| `devit dev` | `pip install -e .[dev]` | `uvicorn main:app --reload` | `manage.py runserver` | `sam local start-api` |
| `devit run` | `python -m <module>` | `uvicorn main:app` | `manage.py runserver 0.0.0.0` | `python -m scripts.main` |
| `devit build` | `python -m build` | `pip install -r requirements.txt` | `pip install -r requirements.txt` | `sam build` |
| `devit test` | `pytest -v` | `pytest -v` | `manage.py test` | `pytest -v` |

```bash
devit dev
devit test
devit build
devit run -- --port 9000    # extra args forwarded
```

---

### `devit clean` — Remove artifacts

```bash
devit clean                  # clean cwd
devit clean ./my-project     # clean specific dir
devit clean --dry-run        # preview only
devit clean --include-venv   # also remove .venv
devit clean -y               # skip confirmation
```

Removes: `__pycache__`, `*.pyc`, `.pytest_cache`, `build/`, `dist/`, `*.egg-info`, `.DS_Store`, `*.log`, `node_modules`, `.coverage`, and more.

---

### `devit info` — System snapshot

```bash
devit info
devit info --json
```

Shows: OS, hostname, Python version + executable, active venv/conda env, CPU count + frequency, RAM usage, disk usage.

---

### `devit find` — Fast file search

```bash
devit find "*.py"
devit find "config" -e toml -e ini
devit find "*" --min-size 1mb --newer-than 7    # >1 MB, modified in last 7 days
devit find --dirs-only "src"
devit find "*" -l 500                           # show up to 500 results
```

---

### `devit zip` / `devit unzip` — Archive utilities

```bash
devit zip dist.zip src/ README.md
devit zip dist.zip . -x __pycache__ -x "*.pyc" -l 9
devit unzip dist.zip ./output
devit unzip dist.zip --list     # show contents without extracting
```

---

### `devit env` — Environment variable management

```bash
devit env list                        # list all env vars
devit env list --filter AWS           # filter by keyword
devit env list --json                 # JSON output

devit env export                      # save to .env  (dotenv format)
devit env export vars.json --format json
devit env export activate.sh  --format shell       # bash / zsh
devit env export activate.ps1 --format powershell  # Windows PowerShell
devit env export activate.bat --format cmd         # Windows CMD

devit env diff .env .env.production   # show what changed
```

---

## Tech Stack

| Library | Purpose |
|---|---|
| [click](https://click.palletsprojects.com) | CLI framework |
| [rich](https://rich.readthedocs.io) | Beautiful terminal output, progress bars, tables |
| [questionary](https://questionary.readthedocs.io) | Interactive prompts |
| [psutil](https://github.com/giampaolo/psutil) | System metrics (CPU, RAM, disk) |

---

## Contributing

```bash
git clone https://github.com/dipenpadhiyar/devit-cli
cd devit-cli
pip install -e ".[dev]"
pytest
```

Pull requests are welcome!

---

## License

MIT — see [LICENSE](https://github.com/dipenpadhiyar/devit-cli/blob/main/LICENSE) for details.



