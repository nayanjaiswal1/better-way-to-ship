# Django REST Framework Template

Production-ready Django REST Framework backend template with layered settings, strict type checking, and automated quality gates.

## Stack

| Tool | Purpose |
|---|---|
| Django 5.1 + DRF 3.15 | Web framework and REST API |
| drf-spectacular | OpenAPI 3 schema generation |
| django-filter | Querystring filtering |
| Celery + Redis | Async task queue |
| Gunicorn + WhiteNoise | Production WSGI server and static files |
| Ruff | Linting and formatting (replaces flake8, isort, black) |
| MyPy + django-stubs | Static type checking |
| Pytest + pytest-django | Testing framework |
| Coverage.py | Coverage measurement with 80% threshold |
| pre-commit | Local hook enforcement |
| uv | Fast Python package management |
| GitHub Actions | CI pipeline |

## Repository Structure

```
django-rest-template/
├── .github/
│   └── workflows/
│       └── ci.yml          # Quality, tests, migration check
├── src/
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py     # Shared settings
│   │   │   ├── development.py
│   │   │   ├── production.py  # Security hardening
│   │   │   └── test.py     # Isolated test settings
│   │   ├── celery.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── api/
│   │   ├── exceptions.py   # Consistent error envelope
│   │   └── urls.py
│   └── manage.py
├── tests/
│   ├── conftest.py
│   └── test_health.py
├── .env.example
├── .pre-commit-config.yaml
└── pyproject.toml          # All tool config in one file
```

## Engineering Standards

- **Layered settings**: `base → development / production / test` split
- **python-decouple** for environment variable injection (no `os.environ` scattered in settings)
- **Ruff** replaces flake8 + isort + black with a single fast tool
- **MyPy strict** with `django-stubs` and `djangorestframework-stubs`
- **Consistent error envelope** from custom `exception_handler`
- **Security hardening** in production settings (HSTS, secure cookies, CSP headers)
- **Migration check** runs in CI against a live Postgres container
- **Coverage threshold**: 80% enforced by `[tool.coverage.report] fail_under`

## Developer Workflow

```bash
# Create and activate virtualenv
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows

# Install all dependencies including dev
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install --install-hooks

# Copy and fill environment variables
cp .env.example .env

# Run migrations
python src/manage.py migrate

# Start dev server
python src/manage.py runserver

# Lint and format
ruff check src tests
ruff format src tests

# Type check
mypy src

# Run tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=term-missing
```

## Quality Gates (CI)

| Job | Checks |
|---|---|
| `quality` | Ruff lint, Ruff format check, MyPy strict |
| `test` | Pytest with coverage >= 80%, uploads to Codecov |
| `migrations` | `manage.py migrate --check` against live Postgres |

All three jobs run in parallel on push and PR. Merges to `main` require all three to pass.

## Release Workflow

This template targets deployment via containerization. Use the CI artifact for builds.
Tag releases conventionally: `git tag v1.2.3 && git push origin v1.2.3`.

Pair with a `release.yml` workflow if GitHub Releases are required.
