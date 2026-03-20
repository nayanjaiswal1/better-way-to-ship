# Zero-Downtime Database Migrations

## The Problem

A naive migration can lock tables and take the app down:
```sql
-- ❌ This locks the entire users table — app goes down during deploy
ALTER TABLE users ADD COLUMN phone VARCHAR NOT NULL DEFAULT '';
ALTER TABLE users DROP COLUMN legacy_field;
ALTER TABLE users RENAME COLUMN old_name TO new_name;
```

## The Expand-Contract Pattern

Every breaking change takes **3 deploys** — never break old and new code simultaneously.

```
Phase 1 — Expand:   Add new column/table (backward compatible)
Phase 2 — Migrate:  Backfill data, update app code to use new column
Phase 3 — Contract: Remove old column/table after all deploys succeed
```

---

## Common Patterns

### Adding a column

```python
# ✅ Phase 1 — always nullable or with default
def upgrade():
    op.add_column('users', sa.Column(
        'phone',
        sa.String(20),
        nullable=True,          # NOT NULL comes later — after backfill
    ))

# ✅ Phase 2 — backfill + make NOT NULL
def upgrade():
    # Backfill in batches — never UPDATE all rows at once (table lock)
    op.execute("""
        UPDATE users SET phone = '' WHERE phone IS NULL AND id BETWEEN 1 AND 10000
    """)
    # ... repeat for all batches via script, not migration

    op.alter_column('users', 'phone', nullable=False, server_default='')

# ✅ Phase 3 — nothing to do for add column
```

### Renaming a column

```python
# ✅ Phase 1 — add new column, keep old
def upgrade():
    op.add_column('users', sa.Column('full_name', sa.String, nullable=True))
    op.execute("UPDATE users SET full_name = name")  # backfill immediately if small table
    # App writes to BOTH old (name) and new (full_name)

# ✅ Phase 2 — app reads from new column, writes to both
# (deploy app code changes)

# ✅ Phase 3 — drop old column
def upgrade():
    op.drop_column('users', 'name')
```

### Adding a NOT NULL column

```python
# ❌ This fails if table has existing rows
def upgrade():
    op.add_column('users', sa.Column('tenant_id', sa.BigInteger, nullable=False))

# ✅ Correct pattern
def upgrade():
    # Step 1: add nullable
    op.add_column('users', sa.Column('tenant_id', sa.BigInteger, nullable=True))

# Then backfill via script (not migration):
# UPDATE users SET tenant_id = 1 WHERE tenant_id IS NULL;

# Step 2: add NOT NULL constraint — use NOT VALID to avoid full scan lock
def upgrade():
    op.execute("ALTER TABLE users ADD CONSTRAINT users_tenant_id_not_null CHECK (tenant_id IS NOT NULL) NOT VALID")
    op.execute("ALTER TABLE users VALIDATE CONSTRAINT users_tenant_id_not_null")
    # VALIDATE runs without a full table lock in PostgreSQL
```

### Adding an index

```python
# ❌ Locks table during index build
def upgrade():
    op.create_index('ix_users_email', 'users', ['email'])

# ✅ CONCURRENTLY — no lock, slower but safe for production
def upgrade():
    op.execute("CREATE INDEX CONCURRENTLY ix_users_email ON users (email)")

# Note: CONCURRENTLY cannot run inside a transaction
# Use op.execute directly, not op.create_index
```

### Dropping a column

```python
# ✅ Phase 1 — stop reading/writing column in app code first
# (deploy app code without the column)

# ✅ Phase 2 — then drop
def upgrade():
    op.drop_column('users', 'legacy_field')
    # Safe — app no longer uses it
```

---

## Large Table Backfills

Never run a mass UPDATE in a single transaction — locks entire table.

```python
# scripts/backfill_tenant_id.py
import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import text

BATCH_SIZE = 1000

async def backfill():
    async with AsyncSessionLocal() as session:
        last_id = 0
        while True:
            result = await session.execute(text("""
                UPDATE users
                SET tenant_id = 1
                WHERE id > :last_id
                  AND id <= :last_id + :batch_size
                  AND tenant_id IS NULL
                RETURNING id
            """), {"last_id": last_id, "batch_size": BATCH_SIZE})

            rows = result.fetchall()
            if not rows:
                break

            last_id = max(row[0] for row in rows)
            await session.commit()
            print(f"Backfilled up to id={last_id}")
            await asyncio.sleep(0.1)  # brief pause — don't hammer DB

asyncio.run(backfill())
```

---

## Alembic Config for Production

```python
# alembic/env.py
def run_migrations_online():
    # Use a short lock timeout — fail fast rather than block
    with connectable.connect() as connection:
        connection.execute(text("SET lock_timeout = '5s'"))
        connection.execute(text("SET statement_timeout = '60s'"))

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transaction_per_migration=True,  # each migration in own transaction
        )
        with context.begin_transaction():
            context.run_migrations()
```

---

## Checklist Before Running a Migration

- [ ] Migration is backward compatible (old app code still works after migration)
- [ ] No `ADD COLUMN NOT NULL` without default or backfill
- [ ] Indexes created with `CONCURRENTLY`
- [ ] Large tables backfilled in batches, not bulk UPDATE
- [ ] Tested on a copy of production data
- [ ] Can be rolled back (`downgrade()` implemented)
- [ ] `lock_timeout` set — fails fast if blocked
