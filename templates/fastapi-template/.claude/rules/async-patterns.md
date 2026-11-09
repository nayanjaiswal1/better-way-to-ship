---
description: Async and SQLAlchemy patterns
globs: "src/**/*.py,tests/**/*.py"
alwaysApply: false
---

# Async Patterns

## SQLAlchemy 2.0 Async

```python
# Correct — async session usage
async def get_by_id(session: AsyncSession, id: int) -> MyModel | None:
    result = await session.execute(select(MyModel).where(MyModel.id == id))
    return result.scalar_one_or_none()

# Correct — bulk insert
async def create(session: AsyncSession, data: dict) -> MyModel:
    obj = MyModel(**data)
    session.add(obj)
    await session.flush()  # get DB-assigned id without committing
    await session.refresh(obj)
    return obj
```

## Never
- `session.execute()` without `await`
- `Model.query` (legacy sync pattern)
- `session.commit()` inside repositories (commit happens in `get_db` dependency)
- Mixing sync and async in the same function

## Test async code

```python
# All test functions are async (asyncio_mode = "auto")
async def test_something(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
```
