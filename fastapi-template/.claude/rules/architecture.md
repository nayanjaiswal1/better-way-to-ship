---
description: Layered architecture rules — always enforced
alwaysApply: true
---

# FastAPI Layered Architecture

## Layer Rules

### Router (`src/app/api/v1/`)
- Thin — HTTP in, HTTP out
- Parses request, calls one service method, returns `response_model`
- No business logic, no direct DB access
- No `HTTPException` raised from service — catch `AppError` here

### Service (`src/app/services/`)
- Business logic and orchestration only
- Calls repositories, never touches SQLAlchemy sessions directly
- Raises `AppError` subclasses on domain errors
- Fully unit-testable without HTTP or DB

### Repository (`src/app/repositories/`)
- All database access via SQLAlchemy async ORM
- Returns ORM model instances or domain primitives
- No business logic — pure data access
- Takes `AsyncSession` as constructor argument

### Model (`src/app/models/`)
- SQLAlchemy ORM table definitions only
- Import in `src/app/models/__init__.py` for Alembic discovery
- No methods with business logic

### Schema (`src/app/schemas/`)
- Pydantic v2 models for request validation and response serialization
- Completely separate from ORM models
- Use `model_config = ConfigDict(from_attributes=True)` for ORM → Pydantic conversion

## Dependency Flow
```
Request → Router → Service → Repository → DB
                           ↓
                        Schema ← ORM Model
                           ↓
Response ← Router ←
```
