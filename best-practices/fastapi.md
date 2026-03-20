# FastAPI Best Practices

## Configuration — pydantic-settings

```python
# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn, validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    APP_NAME: str = "MyApp"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Security — no defaults for secrets
    SECRET_KEY: str                     # must be in .env — no default
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: PostgresDsn
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: RedisDsn

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

    # OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # AWS
    AWS_REGION: str = "us-east-1"
    S3_BUCKET: str = ""

    # Sentry
    SENTRY_DSN: str = ""

    # Feature flags
    FLAGFORGE_STORAGE_URL: str = ""

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

settings = Settings()
```

---

## Correlation IDs — Trace Requests End to End

Every request gets a unique ID. Appears in all logs across the entire request lifecycle.

```python
# middleware/correlation.py
from fastapi import Request
import uuid, structlog

async def correlation_id_middleware(request: Request, call_next):
    # Accept from upstream (API gateway, load balancer) or generate
    correlation_id = (
        request.headers.get("X-Correlation-ID") or
        request.headers.get("X-Request-ID") or
        str(uuid.uuid4())
    )
    request.state.correlation_id = correlation_id

    # Bind to structlog context — all logs in this request include it automatically
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id  # return to client
    return response

# main.py
app.middleware("http")(correlation_id_middleware)
```

```python
# Now every log line includes correlation_id automatically
log = structlog.get_logger()
log.info("user_created", user_id=123)
# → {"correlation_id": "abc-123", "user_id": 123, "event": "user_created"}
```

---

## OpenAPI Customization

```python
# main.py
from fastapi import FastAPI

app = FastAPI(
    title="MyApp API",
    version="1.0.0",
    description="Production API for MyApp",
    docs_url=None if settings.is_production else "/api/docs",  # disabled in prod
    redoc_url=None if settings.is_production else "/api/redoc",
    openapi_url="/api/openapi.json",
)

# Tag endpoints by domain
from fastapi import APIRouter

users_router = APIRouter(prefix="/users", tags=["Users"])
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

# Add examples to schemas
class UserCreate(BaseModel):
    email: str
    name: str

    model_config = {
        "json_schema_extra": {
            "examples": [{"email": "john@example.com", "name": "John Doe"}]
        }
    }

# Document response codes
@users_router.get(
    "/{public_id}",
    response_model=UserResponse,
    responses={
        404: {"description": "User not found"},
        403: {"description": "Insufficient permissions"},
    },
    summary="Get user by ID",
    description="Returns a single user. Requires `users:read` permission.",
)
async def get_user(public_id: str): ...
```

---

## API Deprecation

Gracefully sunset old endpoints — give clients time to migrate.

```python
# core/deprecation.py
from fastapi import Response
from datetime import date

def deprecation_headers(
    response: Response,
    sunset_date: str,          # ISO date: "2026-06-01"
    successor: str | None = None,  # URL of replacement endpoint
):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = sunset_date
    if successor:
        response.headers["Link"] = f'<{successor}>; rel="successor-version"'

# api/v1/endpoints/users.py — old endpoint
@router.get("/users/list")  # old URL
async def list_users_deprecated(response: Response, ...):
    deprecation_headers(
        response,
        sunset_date="2026-06-01",
        successor="/api/v2/users",
    )
    # Still works — just warns clients
    return await list_users_v2(...)

# Monitor usage of deprecated endpoints
log.warning("deprecated_endpoint_called", endpoint="/api/v1/users/list", client=request.client.host)
```

---

## Project Structure
```
app/
├── api/              # Route handlers (thin)
├── core/             # Config, security, permissions
├── db/               # Database setup, sessions
├── dependencies/     # FastAPI dependencies
├── models/           # SQLAlchemy ORM models
├── repositories/     # Data access layer
├── schemas/          # Pydantic schemas
├── services/         # Business logic
└── main.py
```

## Architecture (Layered)
```
Router → Service → Repository → Database
```
- **Routers** - HTTP only: parse request, call service, return response
- **Services** - business logic, orchestration
- **Repositories** - all DB queries, returns domain objects
- **Models** - SQLAlchemy ORM tables only
- **Schemas** - Pydantic request/response models only

## Repository Pattern Example

```python
# repositories/user_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list(self, limit: int = 20, cursor: int | None = None) -> list[User]:
        query = select(User).order_by(User.id).limit(limit)
        if cursor:
            query = query.where(User.id > cursor)
        result = await self.session.execute(query)
        return list(result.scalars().all())
```

```python
# services/user_service.py
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserResponse
from app.core.security import hash_password, verify_password
from app.core.exceptions import NotFoundError
from app.models.user import User

class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    async def create_user(self, data: UserCreate) -> UserResponse:
        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
        )
        created = await self.repo.create(user)
        return UserResponse.model_validate(created)

    async def get_user(self, user_id: int) -> UserResponse | None:
        user = await self.repo.get_by_id(user_id)
        return UserResponse.model_validate(user) if user else None

    async def authenticate_user(self, email: str, password: str) -> User:
        """Verify credentials and return user. Raises NotFoundError if invalid."""
        user = await self.repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise NotFoundError("User")
        return user
```

```python
# api/v1/endpoints/users.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserResponse

router = APIRouter()

async def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db))

@router.post("/", response_model=UserResponse)
async def create_user(
    data: UserCreate,
    service: UserService = Depends(get_user_service),
):
    return await service.create_user(data)
```

## Performance
- **Async all the way** - use `async def` for I/O-bound route handlers; note that `def` handlers run in a threadpool automatically, so only use `async def` when you have actual async I/O (e.g., async DB calls)
- **Connection pooling** - use PgBouncer between app and database
- Use **ARQ or Celery** for background jobs (not in-process BackgroundTasks)
- Use **Gunicorn with UvicornWorker** for production (handles worker crashes properly) — or `uvicorn --workers N` with N = 2-4 x CPU cores
- Enable **Gzip compression** middleware
- Use **eager loading** (selectinload) to prevent N+1 queries
- Route **reads to replicas**, writes to primary

## Database
- Use **SQLAlchemy 2.0** with async (`asyncpg`)
- **Dependency injection** for db sessions
- **Indexes** on frequently queried columns
- Use **bulk operations** for batch inserts/updates
- **Repository pattern** - queries in repositories, logic in services

## API Design (Server-Driven UI Support)

### Response Wrapper Pattern
Every API response should include metadata:

```python
# schemas/common.py
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class APIResponse(BaseModel, Generic[T]):
    data: T
    meta: "ResponseMeta"

class ResponseMeta(BaseModel):
    request_id: str | None = None
    tenant: str | None = None
    pagination: "PaginationMeta" | None = None
    permissions: list["Permission"] = []
    filters: list["FilterDef"] = []
    columns: list["ColumnDef"] = []
    form_schema: dict | None = None
    actions: list["ActionDef"] = []          # row/bulk actions
    navigation: list["NavItem"] = []         # sidebar/menu (app-level endpoint)
    widgets: list["WidgetDef"] = []          # dashboard layout

class PaginationMeta(BaseModel):
    total: int
    next_cursor: str | None = None
    prev_cursor: str | None = None
    limit: int

class Permission(BaseModel):
    resource: str
    actions: list[str]
    fields: dict[str, dict[str, bool]] | None = None

class FilterDef(BaseModel):
    field: str
    type: str  # select, text, date-range, number
    label: str
    options: list[dict] | None = None
    operators: list[str] | None = None

class ColumnDef(BaseModel):
    field: str
    label: str
    sortable: bool = False
    filterable: bool = False
    render: str | None = None  # text, badge, link, image, currency
    render_options: dict | None = None  # e.g. badge color map: {"active": "green", "inactive": "red"}
    width: int | None = None
    align: str = "left"

class ActionDef(BaseModel):
    key: str                          # e.g. "delete", "export"
    label: str
    variant: str = "default"          # default, danger, primary
    bulk: bool = False                # True = bulk action, False = row action
    confirm: str | None = None        # confirmation message if required

class NavItem(BaseModel):
    key: str
    label: str
    path: str
    icon: str | None = None
    children: list["NavItem"] = []

class WidgetDef(BaseModel):
    type: str                         # e.g. "stat", "chart", "table"
    title: str
    config: dict = {}                 # widget-specific config (endpoint, size, etc.)

class ResourceSchema(BaseModel):
    """Returned by /schema endpoints — cached aggressively, separate from data."""
    filters: list[FilterDef] = []
    columns: list[ColumnDef] = []
    actions: list[ActionDef] = []
    permissions: list[Permission] = []
```

```python
# dependencies/common.py
from app.schemas.common import APIResponse, ResponseMeta, PaginationMeta, Permission

async def get_response_meta() -> ResponseMeta:
    return ResponseMeta(request_id=None)

# Using the wrapper in endpoints
@router.get("/users", response_model=APIResponse[list[UserResponse]])
async def list_users(
    cursor: str | None = None,
    limit: int = 20,
    service: UserService = Depends(get_user_service),
    meta: ResponseMeta = Depends(get_response_meta),
):
    users = await service.list_users(cursor=cursor, limit=limit)
    meta.pagination = PaginationMeta(total=users.total, next_cursor=users.next_cursor, limit=limit)
    meta.permissions = [
        Permission(resource="users", actions=["create", "read", "update", "delete"]),
    ]
    return APIResponse(data=users.items, meta=meta)
```

```typescript
// React consuming the response
interface APIResponse<T> {
  data: T;
  meta: {
    request_id: string | null;
    permissions: Array<{ resource: string; actions: string[] }>;
    filters: Array<{ field: string; type: string; options?: any[] }>;
    columns: Array<{ field: string; label: string; render?: string }>;
    pagination?: { total: number; next_cursor: string | null };
  };
}

function useUsers() {
  return useQuery<APIResponse<User[]>>({
    queryKey: ['users'],
    queryFn: () => fetch('/api/v1/users').then(r => r.json()),
  });
}

// Consuming permissions from backend (NOT hardcoded in UI)
function UserActions({ userId }: { userId: number }) {
  const { data } = useUsers();
  const permissions = data?.meta.permissions.find(p => p.resource === 'users');

  // UI NEVER checks user.role === 'admin'
  // Backend controls what's allowed
  return (
    <div>
      {permissions?.actions.includes('delete') && <DeleteButton />}
      {permissions?.actions.includes('update') && <EditButton />}
    </div>
  );
}
```

### Pagination
- Use **cursor-based pagination** for scalability
- `WHERE id > last_seen_id ORDER BY id` instead of `OFFSET N`
- Cursor is opaque, usually last item's ID or a timestamp
- Consistent under concurrent inserts/deletes

### Schema Endpoint
Every resource exposes a `/schema` endpoint returning `ResourceSchema` — cached 30 min on the client:
- Filters, columns, actions, permissions for the resource
- **Never mixed into the data response** — cached separately with a longer staleTime

### Bootstrap Endpoint
Single `GET /api/v1/bootstrap` call on app start returns:
- Current user
- Feature flags
- Navigation items

Replaces 3 separate startup calls. See [api-patterns.md](./api-patterns.md) for full implementation.

## Security
- **Validate all input** with Pydantic models
- **Hash passwords** with `pwdlib` or `bcrypt` directly
- **JWT in httpOnly cookies** — never localStorage (XSS vulnerable)
- **Refresh token rotation** — short-lived access tokens, rotated refresh tokens
- **Token revocation** — invalidate on logout, password change
- **Rate limiting** middleware
- **CORS** configuration for allowed origins only
- **SQL injection prevention** - always use parameterized queries
- **Secrets from secrets manager** — not plain environment variables
- **CSP (Content Security Policy)** header
- **Audit logging** for sensitive actions
- `SECRET_KEY` has **no default** - must be in `.env`
- Docs (`/api/docs`) **disabled in production**

## Error Handling
- **Custom exception handlers** via `@app.exception_handler()`
- Use **AppError subclasses** - never HTTPException from services
- Never leak **stack traces** in production
- Log errors with **structured logging** (structlog)
- **Consistent error format** for all responses

```python
# core/exceptions.py

class AppError(Exception):
    status_code: int = 400

    def __init__(self, message: str, code: str = "ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)

class NotFoundError(AppError):
    status_code = 404

    def __init__(self, resource: str):
        super().__init__(f"{resource} not found", "NOT_FOUND")

class ForbiddenError(AppError):
    status_code = 403

    def __init__(self, message: str = "Access denied"):
        super().__init__(message, "FORBIDDEN")

class AppValidationError(AppError):
    """Named AppValidationError to avoid conflict with pydantic.ValidationError."""
    status_code = 422

    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR")
```

```python
# main.py
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.exceptions import AppError

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=getattr(exc, "status_code", 400),
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request.state.request_id if hasattr(request.state, "request_id") else None,
            }
        },
    )

async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors(),
            }
        },
    )

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
```

```python
# services/user_service.py - DON'T use HTTPException here
# ✅ CORRECT: Raise AppError from services
from app.core.exceptions import NotFoundError

class UserService:
    async def get_user(self, user_id: int) -> User:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User")  # NOT HTTPException!
        return user
```

## Production Checklist
- Run behind **HTTPS** (Traefik, Nginx proxy)
- Use a **secrets manager** for secrets (see [security.md](./security.md))
- Use `--workers` flag or `WEB_CONCURRENCY` env var for worker count
- Enable **request logging**
- Use **health check endpoint** (`/health`)
- **Graceful shutdown** configuration

---

## FastAPI Checklist

### Security
- [ ] JWT in httpOnly cookies
- [ ] Refresh token rotation
- [ ] Secrets from secrets manager
- [ ] Audit logging
- [ ] CSP headers (configured at web server/reverse proxy level, not FastAPI)

### Scalability
- [ ] Alembic migrations
- [ ] ARQ/Celery background jobs
- [ ] Redis caching
- [ ] PgBouncer connection pooling
- [ ] Read replica routing

### Maintainability
- [ ] API versioning strategy
- [ ] Type sharing (openapi-typescript)
- [ ] Contract testing
- [ ] OpenTelemetry tracing
- [ ] Prometheus metrics
- [ ] Feature flag cleanup process
- [ ] Environment parity (Docker)
