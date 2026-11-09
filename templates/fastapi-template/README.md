# FastAPI Template

Production-ready async FastAPI backend template with SQLAlchemy 2.0, Alembic, Pydantic v2, structured logging, JWT auth, and full CI/CD.

## Stack

| Tool | Purpose |
|---|---|
| FastAPI 0.135 | Async web framework with OpenAPI auto-docs |
| Pydantic v2 | Request/response validation and settings |
| SQLAlchemy 2.0 (async) | ORM with full async support |
| asyncpg | High-performance async PostgreSQL driver |
| Alembic | Database migration management |
| structlog | Structured JSON logging (dev: pretty, prod: JSON) |
| python-jose + passlib | JWT creation/validation and bcrypt hashing |
| Redis | Cache and Celery broker |
| Celery | Async task queue |
| Ruff 0.15 | Lint + format (replaces flake8, isort, black) |
| MyPy 1.14 (strict) | Static type checking + pydantic mypy plugin |
| pytest-asyncio | Async test runner (auto mode) |
| httpx AsyncClient | Async HTTP test client |
| uv | Fast Python package manager with lockfile |
| pre-commit | Local quality enforcement |
| GitHub Actions | CI pipeline |
| GitLab CI | Equivalent pipeline with SAST/secret scanning |

## Repository Structure

```
fastapi-template/
├── .github/workflows/ci.yml        # quality, test, migration check
├── .gitlab-ci.yml                  # GitLab equivalent
├── .gitlab/merge_request_templates/
├── .cursor/rules/                  # Cursor IDE AI rules
├── .claude/rules/                  # Claude Code AI rules
├── .vscode/                        # settings, extensions, launch configs
├── .devcontainer/devcontainer.json # Dev Container
├── alembic/
│   ├── env.py                      # Async Alembic environment
│   ├── script.py.mako
│   └── versions/                   # Generated migration files
├── src/
│   └── app/
│       ├── api/
│       │   └── v1/
│       │       ├── __init__.py     # Registers all v1 routers
│       │       └── health.py       # Health-check endpoint
│       ├── core/
│       │   ├── config.py           # Pydantic Settings (reads .env)
│       │   ├── exceptions.py       # AppError hierarchy + handlers
│       │   ├── logging.py          # structlog configuration
│       │   └── security.py         # JWT + bcrypt utilities
│       ├── db/
│       │   └── base.py             # Async engine, session factory, Base
│       ├── dependencies/
│       │   ├── auth.py             # JWT auth dependency
│       │   └── db.py               # Async DB session dependency
│       ├── models/                 # SQLAlchemy ORM models
│       ├── repositories/           # All DB queries
│       ├── schemas/                # Pydantic request/response models
│       ├── services/               # Business logic
│       └── main.py                 # App factory + lifespan
├── tests/
│   ├── conftest.py                 # Shared fixtures (engine, session, client)
│   ├── unit/
│   │   ├── test_health.py
│   │   └── test_security.py
│   └── integration/
│       └── test_db.py
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── alembic.ini
├── CLAUDE.md
└── pyproject.toml                  # All tool config in one file
```

## Architecture

Strict layered architecture — every layer has one responsibility:

```
HTTP Request
    ↓
Router (src/app/api/v1/)     — parse input, call service, return response
    ↓
Service (src/app/services/)  — business logic, orchestration
    ↓
Repository (src/app/repositories/) — all DB access via SQLAlchemy
    ↓
ORM Model (src/app/models/)  — table definitions
```

Pydantic schemas (`src/app/schemas/`) are **separate** from ORM models and used only at the router boundary.

## Engineering Standards

- **Async-first** — all I/O is `async def`, SQLAlchemy async engine, asyncpg driver
- **Pydantic v2** — `model_config = ConfigDict(...)`, no legacy `Config` class
- **`from __future__ import annotations`** in every file
- **Layered architecture** — routers never touch DB, services never raise `HTTPException`
- **Alembic autogenerate** — models are auto-detected via `app/models/__init__.py` import
- **Transactional tests** — test DB session rolls back after each test, no data leakage
- **Structured logging** — pretty in dev, JSON in production (structlog)
- **Docs disabled in production** — `/api/docs` only available when `APP_ENV != production`
- **`SECRET_KEY` has no default** — startup fails if not provided

## Developer Workflow

```bash
# Install dependencies
pip install uv
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install --install-hooks

# Copy and fill environment variables
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY and DATABASE_URL

# Apply migrations
uv run alembic upgrade head

# Start dev server
uv run uvicorn app.main:app --reload

# Type check
uv run mypy src

# Lint and format
uv run ruff check src tests alembic
uv run ruff format src tests alembic

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=app --cov-report=term-missing

# Create a new migration after model changes
uv run alembic revision --autogenerate -m "add users table"

# Verify no pending migration changes
uv run alembic check
```

## Quality Gates (CI)

| Job | Checks |
|---|---|
| `quality` | Ruff lint, Ruff format, MyPy strict |
| `test` | pytest-asyncio with coverage >= 80%, Redis + Postgres services |
| `migrations` | `alembic upgrade head` + `alembic check` against live Postgres |

All three jobs run in parallel on push and PR to `main`/`develop`.

## API

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/v1/health` | GET | None | Health check |
| `/api/docs` | GET | None | Swagger UI (dev only) |
| `/api/openapi.json` | GET | None | OpenAPI schema (dev only) |

## Release Workflow

Tag releases with semver:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Pair with a container registry push workflow for Docker image releases.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | 32-byte hex random string |
| `DATABASE_URL` | Yes | — | `postgresql+asyncpg://...` |
| `APP_ENV` | No | `development` | `development\|staging\|production\|test` |
| `DEBUG` | No | `false` | Must be `false` in production |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection string |
| `LOG_LEVEL` | No | `INFO` | Log verbosity |
| `LOG_JSON` | No | `true` | `false` for pretty dev output |
| `CORS_ORIGINS` | No | `[]` | Allowed CORS origins |
