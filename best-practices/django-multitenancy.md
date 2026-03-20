# Django Multitenancy

## Tenant Model

```python
# apps/tenants/models.py
from django.db import models
from common.models import TimestampedModel
from common.ulid import new_ulid

class Tenant(TimestampedModel):
    public_id   = models.CharField(max_length=26, unique=True, default=new_ulid, editable=False)
    name        = models.CharField(max_length=255)
    slug        = models.SlugField(unique=True)
    plan        = models.CharField(max_length=20, default="free", choices=[
        ("free",       "Free"),
        ("pro",        "Pro"),
        ("enterprise", "Enterprise"),
    ])
    brand_color = models.CharField(max_length=7, blank=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        db_table = "tenants"

    def __str__(self):
        return self.name
```

---

## Tenant Context — Thread/Async Safe

```python
# common/tenant_context.py
from contextvars import ContextVar

_current_tenant_id: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)

def set_current_tenant_id(tenant_id: int | None) -> None:
    _current_tenant_id.set(tenant_id)

def get_current_tenant_id() -> int | None:
    return _current_tenant_id.get()

def require_tenant_id() -> int:
    tid = _current_tenant_id.get()
    if tid is None:
        raise RuntimeError("No tenant context — TenantMiddleware not active")
    return tid
```

---

## Tenant-Scoped Manager

Every model that belongs to a tenant uses this manager.

```python
# common/models.py
from django.db import models
from .tenant_context import get_current_tenant_id

class TenantScopedManager(models.Manager):
    """
    Auto-scope all queries to the current tenant.
    Never returns rows from other tenants.
    Also excludes soft-deleted rows.
    """
    def get_queryset(self):
        tenant_id = get_current_tenant_id()
        qs = super().get_queryset().filter(deleted_at__isnull=True)
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        return qs

class AllObjectsManager(models.Manager):
    """Bypass tenant scoping — for admin, migrations, background jobs."""
    def get_queryset(self):
        return super().get_queryset()

class TenantScopedModel(TimestampedModel):
    tenant     = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="+")
    public_id  = models.CharField(max_length=26, unique=True, default=new_ulid, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects     = TenantScopedManager()   # default — always tenant-scoped
    all_objects = AllObjectsManager()     # bypass — admin/internal use only

    class Meta:
        abstract = True
```

```python
# apps/orders/models.py — inherits scoping automatically
from common.models import TenantScopedModel
from django.db import models

class Order(TenantScopedModel):
    reference = models.CharField(max_length=20, unique=True)
    amount    = models.DecimalField(max_digits=10, decimal_places=2)
    status    = models.CharField(max_length=20, default="pending")

    class Meta:
        db_table = "orders"
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "created_at"]),
        ]

# Usage — automatically scoped to current tenant:
# Order.objects.all()  → SELECT * FROM orders WHERE tenant_id = {current} AND deleted_at IS NULL
# Order.objects.get(public_id=uid)  → includes tenant_id filter automatically
```

---

## Tenant Middleware

```python
# common/middleware.py
from django.utils.deprecation import MiddlewareMixin
from .tenant_context import set_current_tenant_id
import structlog

logger = structlog.get_logger()

class TenantMiddleware(MiddlewareMixin):
    """
    Set tenant context from authenticated user on every request.
    Also binds tenant_id to structured log context.
    """
    def process_request(self, request):
        if hasattr(request, "user") and request.user.is_authenticated:
            set_current_tenant_id(request.user.tenant_id)
            structlog.contextvars.bind_contextvars(
                tenant_id=request.user.tenant_id,
                user_id=request.user.id,
            )

    def process_response(self, request, response):
        # Reset context after each request — don't leak between requests
        set_current_tenant_id(None)
        return response
```

---

## PostgreSQL Row-Level Security (Secondary Defense)

```sql
-- migration: enable RLS on all tenant tables
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Policy: only see rows matching current tenant setting
CREATE POLICY tenant_isolation ON orders
    USING (tenant_id = current_setting('app.current_tenant_id', true)::int);

-- Service role bypasses RLS for migrations/admin
ALTER TABLE orders FORCE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON orders TO app_user;
```

```python
# common/db.py — set tenant setting on each DB connection
from django.db import connection

def set_rls_tenant(tenant_id: int):
    """Set PostgreSQL session variable for RLS."""
    with connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant_id = %s", [tenant_id])
```

```python
# common/middleware.py — add RLS setup
class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if hasattr(request, "user") and request.user.is_authenticated:
            tid = request.user.tenant_id
            set_current_tenant_id(tid)
            # Also set PostgreSQL session variable for RLS
            set_rls_tenant(tid)
```

---

## Tenant-Aware Cache

Prefix every cache key with tenant ID — never leak between tenants.

```python
# common/cache.py
from django.core.cache import cache
from .tenant_context import require_tenant_id

class TenantCache:
    """Cache wrapper that auto-prefixes keys with tenant ID."""

    @staticmethod
    def _key(key: str) -> str:
        tenant_id = require_tenant_id()
        return f"tenant:{tenant_id}:{key}"

    @staticmethod
    def get(key: str):
        return cache.get(TenantCache._key(key))

    @staticmethod
    def set(key: str, value, timeout: int = 300):
        cache.set(TenantCache._key(key), value, timeout)

    @staticmethod
    def delete(key: str):
        cache.delete(TenantCache._key(key))

    @staticmethod
    def delete_pattern(pattern: str):
        """Delete all cache keys matching pattern for current tenant."""
        tenant_id = require_tenant_id()
        full_pattern = f"tenant:{tenant_id}:{pattern}"
        # Requires django-redis
        cache.delete_pattern(full_pattern)

# Usage
tenant_cache = TenantCache()

def get_dashboard_stats():
    stats = tenant_cache.get("dashboard:stats")
    if stats is None:
        stats = _compute_stats()
        tenant_cache.set("dashboard:stats", stats, timeout=300)
    return stats
```

---

## Celery Tasks — Tenant Context

Background jobs lose the request context. Pass tenant_id explicitly.

```python
# apps/orders/tasks.py
from celery import shared_task
from common.tenant_context import set_current_tenant_id

@shared_task
def process_order_export(tenant_id: int, order_ids: list[int]) -> None:
    """Always pass tenant_id to tasks — never rely on request context."""
    # Restore tenant context in the worker
    set_current_tenant_id(tenant_id)

    from apps.orders.models import Order
    orders = Order.objects.filter(id__in=order_ids)  # now tenant-scoped
    # ... generate export

# Calling from a view:
process_order_export.delay(
    tenant_id=request.user.tenant_id,
    order_ids=[o.id for o in orders],
)
```

---

## Tenant Isolation Tests

```python
# apps/orders/tests/test_tenant_isolation.py
import pytest
from rest_framework import status
from apps.orders.tests.factories import OrderFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

class TestTenantIsolation:
    def test_cannot_read_other_tenant_orders(self, auth_client, user):
        # Create order in a different tenant
        other_order = OrderFactory()  # different tenant via factory
        assert other_order.tenant_id != user.tenant_id

        response = auth_client.get(f"/api/v1/orders/{other_order.public_id}/")
        # Returns 404 — does not leak that the order exists
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_order_list_scoped_to_tenant(self, auth_client, user, tenant):
        # Own tenant's orders
        own_orders = OrderFactory.create_batch(3, tenant=tenant)
        # Other tenant's orders
        OrderFactory.create_batch(5)

        response = auth_client.get("/api/v1/orders/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["pagination"]["total"] == 3

    def test_cannot_create_order_for_other_tenant(self, auth_client, user):
        other_tenant = TenantFactory()
        response = auth_client.post("/api/v1/orders/", {
            "tenant_id": other_tenant.id,  # try to inject different tenant
            "amount": "99.00",
        })
        assert response.status_code == status.HTTP_201_CREATED
        # Tenant was set from request user, not from body
        from apps.orders.models import Order
        order = Order.objects.get(public_id=response.data["public_id"])
        assert order.tenant_id == user.tenant_id
```

---

## Multitenancy Checklist

- [ ] All tenant-scoped models inherit `TenantScopedModel`
- [ ] `TenantScopedManager` as default manager — never need to add `.filter(tenant=...)`
- [ ] `AllObjectsManager` available for admin and background jobs
- [ ] `TenantMiddleware` runs on every request — sets context from authenticated user
- [ ] Celery tasks receive `tenant_id` explicitly — never rely on context
- [ ] Cache keys prefixed with `tenant:{id}:` — `TenantCache` wrapper
- [ ] PostgreSQL RLS enabled as secondary defense
- [ ] Cross-tenant access returns 404 — not 403 (don't reveal existence)
- [ ] Tenant isolation tested: list endpoints, detail endpoints, create endpoints
- [ ] Tenant context cleared in `process_response` — no leakage between requests
- [ ] Soft deletes — `deleted_at` — TenantScopedManager excludes them automatically
