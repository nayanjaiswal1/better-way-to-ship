# Python Package Best Practices

## Naming & Structure
- Use a `src/` layout to avoid import confusion during development
- Name the package with underscores (`my_pkg`), the distribution with hyphens (`my-pkg`)
- Keep a single top-level package; avoid deep nesting

## Versioning
- Follow [SemVer](https://semver.org): `MAJOR.MINOR.PATCH`
- Single source of truth: set version only in `pyproject.toml` and read it via `importlib.metadata`
- Maintain a `CHANGELOG.md` (Keep a Changelog format)

## Metadata (`pyproject.toml`)
- Fill `description`, `license`, `authors`, `keywords`, and `classifiers`
- Pin `requires-python` (e.g. `>=3.9`)
- Declare all optional deps under `[project.optional-dependencies]` (e.g. `dev`, `test`)

## Public API
- Explicitly define `__all__` in `__init__.py`
- Ship a `py.typed` marker file to signal PEP 561 compliance
- Add type annotations to all public functions

## Testing
- Aim for >80% coverage; test the installed package, not source files directly
- Use `pytest` with `pytest-cov`

## Releasing
- Build with `python -m build`, check with `twine check dist/*`
- Use trusted publishing (OIDC) to PyPI — avoid storing API tokens in CI secrets
- Tag releases (`vX.Y.Z`) before publishing

## CI Essentials
- Lint: `ruff`
- Type-check: `mypy` or `pyright`
- Test matrix: at least the minimum and latest supported Python versions
