# Multi-Tenancy

## Isolation Strategy

| Strategy | Isolation | Cost | Use when |
|----------|-----------|------|----------|
| Schema per tenant | Strong | High (DDL per tenant) | Strict compliance, large tenants |
| Row-level (shared table) | Medium | Low | Most SaaS apps |
| Database per tenant | Strongest | Very high | Enterprise, regulated industries |

**Default: Row-level isolation** — one table, `tenant_id` on every row, enforced at every layer.

---

## Tenant Resolution Middleware

```python
# core/tenant.py
from contextvars import ContextVar
from fastapi import Request, HTTPException

current_tenant_id: ContextVar[int] = ContextVar("current_tenant_id")

async def tenant_middleware(request: Request, call_next):
    """Resolve tenant from JWT claim, subdomain, or header."""
    # Option 1: From JWT (recommended — tenant set at login)
    token_data = getattr(request.state, "token_data", None)
    tenant_id = token_data.get("tenant_id") if token_data else None

    # Option 2: From subdomain (acme.yourapp.com → tenant "acme")
    # host = request.headers.get("host", "")
    # subdomain = host.split(".")[0]
    # tenant_id = await resolve_tenant_by_subdomain(subdomain)

    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant not resolved")

    current_tenant_id.set(tenant_id)
    response = await call_next(request)
    return response

# main.py
app.middleware("http")(tenant_middleware)
```

---

## Base Repository — Tenant Always Enforced

```python
# repositories/base.py
from app.core.tenant import current_tenant_id
from app.core.exceptions import ForbiddenError

class TenantRepository:
    """Base repository — automatically scopes all queries to current tenant."""

    def __init__(self, session: AsyncSession, model):
        self.session = session
        self.model = model

    @property
    def tenant_id(self) -> int:
        tid = current_tenant_id.get(None)
        if tid is None:
            raise ForbiddenError("No tenant context")
        return tid

    async def get_by_id(self, record_id: int):
        result = await self.session.execute(
            select(self.model).where(
                self.model.id == record_id,
                self.model.tenant_id == self.tenant_id,  # always scoped
                self.model.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list(self, limit: int = 20, cursor: int | None = None):
        query = (
            select(self.model)
            .where(
                self.model.tenant_id == self.tenant_id,  # always scoped
                self.model.deleted_at.is_(None),
            )
            .order_by(self.model.id)
            .limit(limit)
        )
        if cursor:
            query = query.where(self.model.id > cursor)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, obj):
        obj.tenant_id = self.tenant_id  # always set tenant
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj


# repositories/user_repository.py
class UserRepository(TenantRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    # All base methods (get_by_id, list, create) automatically scoped to tenant
    # Add only user-specific methods here
    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.email == email,
                User.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()
```

---

## PostgreSQL Row-Level Security (Extra Layer)

Defence-in-depth — even if application code has a bug, DB enforces tenant isolation.

```python
# Alembic migration
def upgrade():
    # Enable RLS on table
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")

    # Policy: app_user can only see rows matching their tenant
    op.execute("""
        CREATE POLICY tenant_isolation ON users
        USING (tenant_id = current_setting('app.tenant_id')::int)
    """)

    # App sets tenant before each query
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
```

```python
# db/session.py — set tenant context on each DB connection
from sqlalchemy import event, text

@event.listens_for(AsyncSession, "after_begin")
async def set_tenant_context(session, transaction, connection):
    tid = current_tenant_id.get(None)
    if tid:
        await connection.execute(
            text("SET LOCAL app.tenant_id = :tid"), {"tid": tid}
        )
```

---

## Tenant-Aware Caching

```python
# Always namespace cache keys by tenant
async def get_cached(key: str, tenant_id: int) -> any:
    return await redis.get(f"tenant:{tenant_id}:{key}")

async def set_cached(key: str, tenant_id: int, value: any, ttl: int = 300):
    await redis.setex(f"tenant:{tenant_id}:{key}", ttl, json.dumps(value))
```

---

## React — Tenant Context

```tsx
// context/TenantContext.tsx
interface Tenant {
  id: number;
  name: string;
  slug: string;
  logo_url: string | null;
  features: Record<string, boolean>;  // tenant-specific feature overrides
}

const TenantContext = createContext<Tenant | null>(null);

export function useTenant(): Tenant {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error('useTenant must be used within TenantProvider');
  return ctx;
}

// Tenant comes from bootstrap — no extra call needed
export function TenantProvider({ children }: { children: React.ReactNode }) {
  const { data } = useQuery({ queryKey: ['bootstrap'] });

  if (!data?.tenant) return <div>Loading...</div>;

  return (
    <TenantContext.Provider value={data.tenant}>
      {children}
    </TenantContext.Provider>
  );
}

// Usage
function Header() {
  const tenant = useTenant();
  return (
    <header>
      {tenant.logo_url && <img src={tenant.logo_url} alt={tenant.name} />}
      <h1>{tenant.name}</h1>
    </header>
  );
}
```

---

## Checklist

- [ ] `tenant_id` on every user-data table
- [ ] `TenantRepository` base class enforces scoping — no raw queries bypass it
- [ ] PostgreSQL RLS enabled as secondary defence
- [ ] Cache keys namespaced by tenant
- [ ] Bootstrap returns tenant config
- [ ] Feature flags support per-tenant overrides (already in feature-flags.md)
- [ ] Indexes include `tenant_id` as first column in composite indexes
