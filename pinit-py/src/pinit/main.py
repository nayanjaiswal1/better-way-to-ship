"""pinit — scaffold Python projects from production-ready templates."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = "nayanjaiswal1/project-templates"
BRANCH = "master"

TEMPLATES = {
    "fastapi": {
        "folder": "fastapi-template",
        "description": "FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2",
        "placeholder_name": "app",
    },
    "django": {
        "folder": "django-rest-template",
        "description": "Django 5.2 + Django REST Framework 3.16",
        "placeholder_name": "myproject",
    },
    "pypackage": {
        "folder": "python-package-template",
        "description": "Python package with src layout, Hatchling, PyPI OIDC publish",
        "placeholder_name": "mypkg",
    },
}

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"


def print_banner() -> None:
    print(f"""
{BOLD}{CYAN}pinit{RESET} — Python project scaffolder
""")


def print_templates() -> None:
    print(f"{BOLD}Available templates:{RESET}\n")
    for key, meta in TEMPLATES.items():
        print(f"  {BOLD}{CYAN}{key:<12}{RESET}  {meta['description']}")
    print()


def err(msg: str) -> None:
    print(f"{RED}error:{RESET} {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"{GREEN}>{RESET} {msg}")


def dim(msg: str) -> None:
    print(f"{DIM}{msg}{RESET}")


def download_template(template_folder: str, dest: Path) -> None:
    url = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
    info(f"Downloading template from {REPO}...")

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "repo.zip"

        with urllib.request.urlopen(url) as resp, open(zip_path, "wb") as f:  # noqa: S310
            shutil.copyfileobj(resp, f)

        with zipfile.ZipFile(zip_path) as zf:
            repo_root = f"project-templates-{BRANCH}/{template_folder}/"
            members = [m for m in zf.namelist() if m.startswith(repo_root)]
            if not members:
                err(f"Template folder '{template_folder}' not found in archive.")
                sys.exit(1)

            for member in members:
                rel = member[len(repo_root):]
                if not rel:
                    continue
                target = dest / rel
                if member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)


def rename_in_file(path: Path, old: str, new: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
        if old in text:
            path.write_text(text.replace(old, new), encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        pass


def rename_placeholder(dest: Path, placeholder: str, project_name: str) -> None:
    if placeholder == project_name:
        return
    info(f"Renaming '{placeholder}' -> '{project_name}' across files...")

    # Rename file/dir names that contain the placeholder (deepest first)
    for p in sorted(dest.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        if placeholder in p.name:
            new_name = p.name.replace(placeholder, project_name)
            p.rename(p.parent / new_name)

    # Replace content in all files
    for p in dest.rglob("*"):
        if p.is_file():
            rename_in_file(p, placeholder, project_name)


def init_git(dest: Path) -> None:
    info("Initialising git repository...")
    try:
        subprocess.run(["git", "init"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=dest, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "chore: initial project scaffold from pinit"],
            cwd=dest,
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        dim("  (git not available — skipping initial commit)")


def validate_name(name: str) -> bool:
    return bool(re.match(r"^[a-z][a-z0-9_-]*$", name))


def usage() -> None:
    print_banner()
    print_templates()
    print(f"{BOLD}Usage:{RESET}")
    print("  pinit <template> <project-name>\n")
    print(f"{BOLD}Examples:{RESET}")
    print("  pinit fastapi my-api")
    print("  pinit django my-site")
    print("  pinit pypackage my-lib")
    print()
    print(f"{DIM}Run with uvx: uvx pinit fastapi my-api{RESET}")
    print()


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        usage()
        sys.exit(0)

    if args[0] in ("--version", "-V"):
        from pinit import __version__
        print(__version__)
        sys.exit(0)

    if len(args) < 2:
        err("provide both a template name and a project name.")
        print()
        usage()
        sys.exit(1)

    template_key = args[0].lower()
    project_name = args[1]

    if template_key not in TEMPLATES:
        err(f"unknown template '{template_key}'")
        print()
        print_templates()
        sys.exit(1)

    if not validate_name(project_name):
        err(f"invalid project name '{project_name}' — use lowercase letters, numbers, hyphens, underscores only, starting with a letter.")
        sys.exit(1)

    dest = Path.cwd() / project_name
    if dest.exists():
        err(f"directory '{project_name}' already exists.")
        sys.exit(1)

    meta = TEMPLATES[template_key]
    dest.mkdir(parents=True)

    try:
        download_template(meta["folder"], dest)
        rename_placeholder(dest, meta["placeholder_name"], project_name.replace("-", "_"))
        init_git(dest)
    except KeyboardInterrupt:
        shutil.rmtree(dest, ignore_errors=True)
        print("\nAborted.")
        sys.exit(1)
    except Exception as exc:
        shutil.rmtree(dest, ignore_errors=True)
        err(str(exc))
        sys.exit(1)

    print(f"""
{BOLD}{GREEN}Done!{RESET} Project created at {BOLD}{dest}{RESET}

{BOLD}Next steps:{RESET}
  cd {project_name}
  uv sync --all-extras
""")

    if template_key == "fastapi":
        print(f"  cp .env.example .env   {DIM}# fill in SECRET_KEY{RESET}")
        print(f"  uv run uvicorn {project_name.replace('-', '_')}.main:app --reload")
    elif template_key == "django":
        print(f"  cp .env.example .env")
        print(f"  uv run python src/manage.py migrate")
        print(f"  uv run python src/manage.py runserver")
    elif template_key == "pypackage":
        print(f"  uv run pytest")
        print(f"  uv build")

    print()
