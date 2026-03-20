# Database Sharding

Sharding splits data across multiple database instances. Use it only when a single PostgreSQL instance (even with read replicas and connection pooling) can no longer handle your write throughput or storage.

## When to Shard

| Try first | Then shard |
|-----------|-----------|
| Add indexes | Write throughput > 50k writes/sec sustained |
| Connection pooling (PgBouncer) | Storage > 10TB on a single instance |
| Read replicas for read scaling | Single-row hotspots that can't be mitigated |
| Vertical scaling (larger instance) | Regulatory: data must live in specific regions |
| Table partitioning (same instance) | |

**Most SaaS products never need sharding.** Table partitioning (see below) solves 90% of scale problems within a single Postgres instance.

---

## Table Partitioning — Try This First

PostgreSQL native, no application changes needed.

```sql
-- Partition orders by tenant_id ranges (horizontal partition, same DB)
CREATE TABLE orders (
    id         BIGSERIAL,
    tenant_id  INTEGER NOT NULL,
    public_id  VARCHAR(26) NOT NULL,
    amount     NUMERIC(10,2),
    status     VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
) PARTITION BY RANGE (tenant_id);

-- Create partitions — each covers a range of tenant_ids
CREATE TABLE orders_p1 PARTITION OF orders FOR VALUES FROM (1)      TO (10001);
CREATE TABLE orders_p2 PARTITION OF orders FOR VALUES FROM (10001)   TO (20001);
CREATE TABLE orders_p3 PARTITION OF orders FOR VALUES FROM (20001)   TO (30001);

-- Queries automatically hit only the relevant partition
EXPLAIN SELECT * FROM orders WHERE tenant_id = 500;
-- → Seq Scan on orders_p1 (skips p2, p3)
```

```sql
-- Partition by time (common for append-heavy tables like events, logs)
CREATE TABLE events (
    id         BIGSERIAL,
    tenant_id  INTEGER NOT NULL,
    event_type VARCHAR(50),
    payload    JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
) PARTITION BY RANGE (created_at);

CREATE TABLE events_2026_01 PARTITION OF events
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE events_2026_02 PARTITION OF events
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- pg_partman automates partition creation and old partition archival
```

```bash
pip install django-pg-partitioning   # Django
# or manage partitions via Alembic migrations for FastAPI
```

---

## Sharding Strategies

### 1. Tenant-Based Sharding (Best for SaaS)

Each tenant's data lives on one shard. Simple, no cross-shard queries needed.

```
Shard 0: tenant_id % 4 == 0  →  DB: postgres-shard-0
Shard 1: tenant_id % 4 == 1  →  DB: postgres-shard-1
Shard 2: tenant_id % 4 == 2  →  DB: postgres-shard-2
Shard 3: tenant_id % 4 == 3  →  DB: postgres-shard-3
```

```python
# core/sharding.py — shard router
from functools import lru_cache
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

SHARD_COUNT = 4

SHARD_URLS = {
    0: settings.DATABASE_SHARD_0_URL,
    1: settings.DATABASE_SHARD_1_URL,
    2: settings.DATABASE_SHARD_2_URL,
    3: settings.DATABASE_SHARD_3_URL,
}

@lru_cache(maxsize=None)
def get_shard_engine(shard_id: int) -> AsyncEngine:
    return create_async_engine(SHARD_URLS[shard_id], pool_size=10)

def shard_for_tenant(tenant_id: int) -> int:
    return tenant_id % SHARD_COUNT

def get_engine_for_tenant(tenant_id: int) -> AsyncEngine:
    return get_shard_engine(shard_for_tenant(tenant_id))

# Context manager — get session for a specific tenant
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_tenant_session(tenant_id: int):
    engine = get_engine_for_tenant(tenant_id)
    async with AsyncSession(engine) as session:
        yield session
```

```python
# Usage in FastAPI — transparent to the endpoint
@router.get("/orders")
async def list_orders(current_user: User = Depends(get_current_user)):
    async with get_tenant_session(current_user.tenant_id) as session:
        orders = await session.execute(
            select(Order).where(Order.tenant_id == current_user.tenant_id)
        )
        return orders.scalars().all()
```

```python
# Django — custom database router
# core/db_router.py
from .sharding import shard_for_tenant
from common.tenant_context import get_current_tenant_id

class TenantShardRouter:
    def db_for_read(self, model, **hints):
        tenant_id = hints.get("tenant_id") or get_current_tenant_id()
        if tenant_id:
            return f"shard_{shard_for_tenant(tenant_id)}"
        return "default"

    def db_for_write(self, model, **hints):
        return self.db_for_read(model, **hints)

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations within the same shard
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True

# config/settings/base.py
DATABASE_ROUTERS = ["core.db_router.TenantShardRouter"]

DATABASES = {
    "default": env.db("DATABASE_URL"),
    "shard_0": env.db("DATABASE_SHARD_0_URL"),
    "shard_1": env.db("DATABASE_SHARD_1_URL"),
    "shard_2": env.db("DATABASE_SHARD_2_URL"),
    "shard_3": env.db("DATABASE_SHARD_3_URL"),
}
```

---

### 2. Consistent Hashing — Rebalancing Without Resharding

Hash ring maps keys to shards. Adding a shard moves minimal data.

```python
# core/consistent_hash.py
import hashlib
from bisect import bisect_right

class ConsistentHashRing:
    """
    Virtual nodes (vnodes) distribute load evenly.
    Adding a shard moves ~1/N data, not 1/2.
    """
    def __init__(self, nodes: list[str], vnodes: int = 150):
        self.vnodes = vnodes
        self.ring: dict[int, str] = {}
        self.sorted_keys: list[int] = []

        for node in nodes:
            self.add_node(node)

    def add_node(self, node: str) -> None:
        for i in range(self.vnodes):
            key = self._hash(f"{node}:{i}")
            self.ring[key] = node
        self.sorted_keys = sorted(self.ring.keys())

    def remove_node(self, node: str) -> None:
        for i in range(self.vnodes):
            key = self._hash(f"{node}:{i}")
            del self.ring[key]
        self.sorted_keys = sorted(self.ring.keys())

    def get_node(self, key: str) -> str:
        if not self.ring:
            raise ValueError("Ring is empty")
        h = self._hash(key)
        idx = bisect_right(self.sorted_keys, h) % len(self.sorted_keys)
        return self.ring[self.sorted_keys[idx]]

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

# Usage
ring = ConsistentHashRing(nodes=["shard-0", "shard-1", "shard-2", "shard-3"])

def get_shard(tenant_id: int) -> str:
    return ring.get_node(str(tenant_id))

# Adding a shard later — only ~25% of tenants move
ring.add_node("shard-4")
```

---

## Shard Lookup Table — For Non-Uniform Distribution

When consistent hashing isn't flexible enough (e.g. large tenants need dedicated shards).

```python
# Shard assignment stored in a central "directory" database
# Only this table is on the main DB — all other data is on shards

class TenantShard(Base):
    __tablename__ = "tenant_shards"
    tenant_id = mapped_column(Integer, primary_key=True)
    shard_id  = mapped_column(Integer, nullable=False)
    # Large tenants can have their own dedicated shard
    # Small tenants share shards

# core/sharding.py
from functools import lru_cache

@lru_cache(maxsize=10000)   # cache shard lookups in memory
async def get_shard_id(tenant_id: int, directory_session) -> int:
    result = await directory_session.get(TenantShard, tenant_id)
    if result:
        return result.shard_id
    # Default assignment for new tenants
    return tenant_id % SHARD_COUNT
```

---

## Migrations Across Shards

```bash
# Run migrations on all shards
# Django
python manage.py migrate --database=shard_0
python manage.py migrate --database=shard_1
python manage.py migrate --database=shard_2
python manage.py migrate --database=shard_3
```

```python
# Makefile / CI script — migrate all shards
migrate-all:
	for shard in 0 1 2 3; do \
		python manage.py migrate --database=shard_$$shard; \
	done
```

```python
# FastAPI — Alembic per-shard
# alembic/env.py
from core.sharding import SHARD_URLS

def run_migrations_for_all_shards():
    for shard_id, url in SHARD_URLS.items():
        print(f"Migrating shard {shard_id}...")
        engine = create_engine(url)
        with engine.begin() as conn:
            context.configure(connection=conn)
            context.run_migrations()
```

---

## Cross-Shard Queries — Avoid, But Handle When Needed

```python
# Scatter-gather: fan out to all shards, aggregate results
# Use sparingly — O(shards) DB calls

async def admin_search_all_tenants(query: str) -> list[dict]:
    """Admin-only: search across all shards."""
    tasks = [
        search_shard(shard_id, query)
        for shard_id in range(SHARD_COUNT)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Flatten and sort
    all_rows = []
    for r in results:
        if not isinstance(r, Exception):
            all_rows.extend(r)
    return sorted(all_rows, key=lambda x: x["created_at"], reverse=True)

async def search_shard(shard_id: int, query: str) -> list[dict]:
    async with AsyncSession(get_shard_engine(shard_id)) as session:
        result = await session.execute(
            select(Tenant).where(Tenant.name.ilike(f"%{query}%"))
        )
        return [t.__dict__ for t in result.scalars()]
```

---

## Resharding — Moving Tenants Between Shards

```python
# scripts/reshard_tenant.py — move a tenant to a different shard
import asyncio

async def migrate_tenant(tenant_id: int, from_shard: int, to_shard: int):
    """
    Zero-downtime tenant migration:
    1. Copy data to target shard
    2. Update shard lookup table
    3. Verify data on target
    4. Delete from source shard
    """
    from_engine = get_shard_engine(from_shard)
    to_engine   = get_shard_engine(to_shard)

    # Step 1: Copy all tenant data
    async with AsyncSession(from_engine) as src, AsyncSession(to_engine) as dst:
        # Copy each table
        for model in [Order, Invoice, User, ...]:
            rows = await src.execute(
                select(model).where(model.tenant_id == tenant_id)
            )
            for row in rows.scalars():
                dst.add(model(**{c.name: getattr(row, c.name) for c in model.__table__.columns}))
        await dst.commit()

    # Step 2: Atomically update shard directory
    async with get_directory_session() as session:
        await session.execute(
            update(TenantShard)
            .where(TenantShard.tenant_id == tenant_id)
            .values(shard_id=to_shard)
        )
        await session.commit()

    # Step 3: Delete from source (after verification)
    async with AsyncSession(from_engine) as src:
        for model in reversed([Order, Invoice, User, ...]):  # FK order
            await src.execute(delete(model).where(model.tenant_id == tenant_id))
        await src.commit()
```

---

## Sharding Checklist

- [ ] Try partitioning first (`PARTITION BY RANGE`) — same DB, no app changes
- [ ] Try read replicas + PgBouncer before sharding — handles most read scale
- [ ] Shard key = `tenant_id` for SaaS — keeps all tenant data on one shard
- [ ] Shard lookup table for large/enterprise tenants needing dedicated shards
- [ ] Consistent hashing if you expect to add shards over time
- [ ] All migrations run on every shard — automated in CI
- [ ] Cross-shard queries are scatter-gather — used only for admin/analytics
- [ ] Resharding script for moving tenants (zero-downtime pattern)
- [ ] Shard ID cached in memory — never a DB lookup on the hot path
- [ ] Monitor shard balance — alert if one shard has > 2x rows of another
