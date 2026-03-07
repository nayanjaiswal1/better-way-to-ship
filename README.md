# Template Repository System — v3

Five minimal, production-ready project templates. Updated March 2026 with the latest stable tooling.

---

## CLI Tools — Scaffold in One Command

Don't clone this repo manually. Use the CLI tools to scaffold any template instantly.

### Python templates (FastAPI, Django, Python package)

```bash
# no install needed
uvx project-pinit fastapi my-api
uvx project-pinit django my-site
uvx project-pinit pypackage my-lib

# or install globally
pip install project-pinit
project-pinit fastapi my-api
```

> PyPI: https://pypi.org/project/project-pinit/

### Node/React templates (React app, Node package)

```bash
# no install needed
npx create-pinit react my-app
npx create-pinit nodepkg my-lib

# or install globally
npm install -g create-pinit
create-pinit react my-app
```

> npm: https://www.npmjs.com/package/create-pinit

Both tools download the template, rename all placeholders to your project name, and run `git init` with an initial commit — ready to push.

## Templates

| Template | Language | Package Manager | CI |
|---|---|---|---|
| `react-app-template/` | TypeScript | pnpm 10 | GitHub Actions + GitLab CI |
| `django-rest-template/` | Python 3.12 | uv | GitHub Actions + GitLab CI |
| `fastapi-template/` | Python 3.12 | uv | GitHub Actions + GitLab CI |
| `python-package-template/` | Python 3.12 | uv | GitHub Actions + GitLab CI |
| `node-package-template/` | TypeScript | pnpm 10 | GitHub Actions + GitLab CI |

---

## What's Included Per Template

Every template ships with:

| Layer | Contents |
|---|---|
| **Source** | Minimal `src/` + `tests/` only |
| **Tooling config** | Linting, formatting, type checking, testing, coverage |
| **Pre-commit / Husky** | Local quality enforcement before every commit |
| **GitHub Actions** | Parallel quality + test + build/release pipeline |
| **GitLab CI** | Equivalent pipeline with SAST, Dependency Scanning, Secret Detection |
| **GitLab MR template** | Structured merge request checklist |
| **VS Code settings** | `settings.json`, `extensions.json`, `launch.json` |
| **Dev Container** | `devcontainer.json` with `ghcr.io` features |
| **AI Agent rules** | `CLAUDE.md` + `.claude/rules/` for Claude Code; `.cursor/rules/*.mdc` for Cursor |
| **README** | Engineering standards + workflow documentation |

---

## Version Reference (March 2026)

### React App
| React | Vite | TypeScript | Vitest | ESLint | pnpm | Node |
|---|---|---|---|---|---|---|
| 19.1 | 7.x | 5.8 | 4.x | 9.x flat | 10.x | 22 LTS |

### Django REST
| Django | DRF | Python | Ruff | MyPy | Postgres |
|---|---|---|---|---|---|
| 5.2 | 3.16 | 3.12 | 0.15.x | 1.14 | 17 |

### FastAPI (NEW)
| FastAPI | Pydantic | SQLAlchemy | Alembic | structlog | pytest-asyncio | Python | Postgres | Redis |
|---|---|---|---|---|---|---|---|---|
| 0.135 | v2.10 | 2.0 async | 1.14 | 24.4 | 0.24 auto | 3.12 | 17 | 7 |

### Python Package
| Python matrix | Hatchling | Ruff | MyPy | Coverage |
|---|---|---|---|---|
| 3.12 / 3.13 | latest | 0.15.x | 1.14 strict | 90% |

### Node Package
| TypeScript | tsdown | Vitest | ESLint | pnpm | Node matrix |
|---|---|---|---|---|---|
| 5.8 | 0.10+ | 4.x | 9.x flat | 10.x | 22 / 24 |

---

## FastAPI vs Django REST

| Factor | FastAPI | Django REST |
|---|---|---|
| Async | Native, first-class | Partial (ASGI optional) |
| ORM | SQLAlchemy 2.0 async | Django ORM (sync) |
| Docs | OpenAPI auto from types | drf-spectacular |
| Admin | None | Built-in |
| Auth | Manual JWT | Built-in |
| Best for | High-throughput APIs, AI backends | Full apps, admin panels |

---

## Quick Start

### React App
```bash
cd react-app-template && pnpm install && pnpm dev
```

### Django REST
```bash
cd django-rest-template
pip install uv && uv sync --all-extras
cp .env.example .env && uv run pre-commit install --install-hooks
uv run python src/manage.py runserver
```

### FastAPI
```bash
cd fastapi-template
pip install uv && uv sync --all-extras
cp .env.example .env   # set SECRET_KEY + DATABASE_URL
uv run pre-commit install --install-hooks
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
# Swagger UI → http://localhost:8000/api/docs
```

### Python Package
```bash
cd python-package-template
pip install uv && uv sync --all-extras
uv run pre-commit install --install-hooks && uv run pytest
```

### Node Package
```bash
cd node-package-template && pnpm install && pnpm build && pnpm test
```
