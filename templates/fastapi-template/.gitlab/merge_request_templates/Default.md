## Summary

<!-- What does this MR do? Why? -->

## Changes

-

## Testing

- [ ] Tests added / updated
- [ ] `uv run pytest --cov=app` passes locally with >= 80% coverage
- [ ] `uv run ruff check src tests alembic` passes
- [ ] `uv run mypy src` passes
- [ ] Migration included if models changed (`uv run alembic revision --autogenerate -m "..."`)
- [ ] `uv run alembic check` passes (no pending model changes without migration)

## Checklist

- [ ] No secrets committed
- [ ] `from __future__ import annotations` in all new files
- [ ] All new endpoints have Pydantic `response_model` set
- [ ] Layered architecture respected (router → service → repository)
- [ ] No raw SQL — use SQLAlchemy ORM or `text()` with parameterised values
- [ ] Conventional commit messages used
