# mypkg — Python Package Template

Production-ready Python package template with PEP 517/518 packaging, strict type checking, multi-version CI, and automated PyPI publishing.

## Stack

| Tool | Purpose |
|---|---|
| Hatchling | Modern PEP 517 build backend |
| uv | Fast Python package management |
| Ruff | Linting + formatting (replaces flake8, isort, black, pydocstyle) |
| MyPy (strict) | Static type checking |
| Pytest + pytest-xdist | Parallel testing |
| Coverage.py | Coverage with 90% threshold |
| pre-commit | Local hook enforcement |
| GitHub Actions | CI + PyPI publishing via OIDC |

## Repository Structure

```
python-package-template/
├── .github/
│   └── workflows/
│       └── ci.yml          # Quality gates, multi-version tests, PyPI publish
├── src/
│   └── mypkg/
│       ├── __init__.py     # Version source of truth
│       └── py.typed        # PEP 561 marker (declares inline types)
├── tests/
│   ├── __init__.py
│   └── test_package.py
├── .pre-commit-config.yaml
├── .gitignore
├── CHANGELOG.md
└── pyproject.toml          # All config: build, ruff, mypy, pytest, coverage
```

## Engineering Standards

- **src layout** prevents accidental imports from the project root
- **`py.typed` marker** (PEP 561) declares the package ships inline types
- **MyPy strict** — `disallow_untyped_defs`, `warn_return_any`, etc.
- **Ruff** enforces docstring conventions (`google`), import ordering, bugbear, bandit
- **Coverage threshold**: 90% (higher bar for libraries vs applications)
- **Multi-version matrix**: Python 3.12 and 3.13 tested in parallel
- **Trusted Publishing** (OIDC) — no stored PyPI API tokens in CI

## Developer Workflow

```bash
# Create virtualenv and install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install --install-hooks

# Lint and format
ruff check src tests
ruff format src tests

# Type check
mypy src

# Run tests
pytest

# Run tests with coverage
pytest --cov=mypkg --cov-report=term-missing

# Build distribution
python -m build   # or: uv build
```

## Quality Gates (CI)

| Job | Checks |
|---|---|
| `quality` | Ruff lint, Ruff format, MyPy strict |
| `test (3.12)` | Pytest + coverage >= 90%, upload to Codecov |
| `test (3.13)` | Pytest (coverage not re-uploaded) |

## Release Workflow

1. Update version in `src/mypkg/__init__.py`
2. Update `CHANGELOG.md`
3. Commit: `git commit -m "chore: release v1.0.0"`
4. Tag: `git tag v1.0.0 && git push origin v1.0.0`

The `publish` CI job triggers automatically on tags matching `v*`, builds the wheel/sdist, and publishes to PyPI using OIDC trusted publishing (no API token required).

Configure trusted publishing in your PyPI project settings before the first release.
