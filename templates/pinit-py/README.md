# pinit

Scaffold production-ready Python projects in one command. No copying, no manual setup.

## Usage

```bash
# with uvx (no install needed)
uvx pinit fastapi my-api
uvx pinit django my-site
uvx pinit pypackage my-lib

# or install globally
pip install pinit
pinit fastapi my-api
```

## Templates

| Template | Stack |
|---|---|
| `fastapi` | FastAPI 0.135 + SQLAlchemy 2.0 async + Alembic + Pydantic v2 + structlog |
| `django` | Django 5.2 + Django REST Framework 3.16 + Celery + Postgres |
| `pypackage` | Python package with src layout, Hatchling, PyPI OIDC publish |

## What you get

Every scaffolded project includes:

- **uv** for dependency management (`uv sync` works immediately)
- **Ruff 0.15** for lint + format, **MyPy 1.14** strict for type checking
- **pre-commit** hooks: trailing whitespace, YAML/TOML check, detect secrets, no commits to main
- **Commitizen** for conventional commit enforcement
- **GitHub Actions CI** (lint + test + migrations) and **GitLab CI** pipelines
- **VS Code settings** — format on save, Ruff as formatter, correct extensions
- **Dev container** — `devcontainer.json` for Codespaces or local container
- **AI agent rules** — `CLAUDE.md`, `.claude/rules/`, `.cursor/rules/` pre-filled
- **No AI attribution** in commits — pre-commit hook blocks `Co-Authored-By: Claude` and similar lines

## After scaffolding

```bash
cd my-api
uv sync --all-extras
cp .env.example .env     # fill in SECRET_KEY
uv run pytest            # all tests pass out of the box
```
