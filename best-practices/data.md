# Data Patterns

## CSV / Excel Export

### Backend — StreamingResponse for large datasets

```bash
pip install openpyxl
```

```python
# services/export_service.py
import csv, io
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

class ExportService:
    async def export_csv(self, tenant_id: int, filters: dict) -> StreamingResponse:
        """Stream CSV — never loads entire dataset into memory."""

        async def generate():
            output = io.StringIO()
            writer = csv.writer(output)

            # Header
            writer.writerow(["ID", "Name", "Email", "Status", "Created At"])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

            # Stream rows in batches — never load all at once
            cursor = None
            while True:
                batch = await self.repo.list(tenant_id, cursor=cursor, limit=500, filters=filters)
                if not batch:
                    break

                for user in batch:
                    writer.writerow([
                        user.public_id,
                        user.name,
                        user.email,
                        user.status,
                        user.created_at.isoformat(),
                    ])

                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

                cursor = batch[-1].id
                if len(batch) < 500:
                    break

        return StreamingResponse(
            generate(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=users.csv"},
        )

    async def export_excel(self, tenant_id: int, filters: dict) -> StreamingResponse:
        """Excel export with styled headers."""
        wb = Workbook()
        ws = wb.active
        ws.title = "Users"

        # Styled header row
        headers = ["ID", "Name", "Email", "Status", "Created At"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="366092")
            cell.alignment = Alignment(horizontal="center")

        # Data rows
        users = await self.repo.list_all(tenant_id, filters=filters)
        for row, user in enumerate(users, 2):
            ws.cell(row=row, column=1, value=user.public_id)
            ws.cell(row=row, column=2, value=user.name)
            ws.cell(row=row, column=3, value=user.email)
            ws.cell(row=row, column=4, value=user.status)
            ws.cell(row=row, column=5, value=user.created_at.isoformat())

        # Auto-width columns
        for col in ws.columns:
            max_length = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=users.xlsx"},
        )
```

```python
# api/v1/endpoints/users.py
@router.get("/export")
async def export_users(
    format: str = Query("csv", pattern="^(csv|excel)$"),
    permissions: PermissionChecker = Depends(get_permissions),
    service: ExportService = Depends(get_export_service),
):
    permissions.require("users", "export")
    if format == "excel":
        return await service.export_excel(tenant_id=current_tenant_id.get())
    return await service.export_csv(tenant_id=current_tenant_id.get(), filters={})
```

```tsx
// React — trigger download
function ExportButton({ format }: { format: 'csv' | 'excel' }) {
  const handleExport = async () => {
    const resp = await fetch(`/api/v1/users/export?format=${format}`, {
      credentials: 'include',
    });
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `users.${format === 'excel' ? 'xlsx' : 'csv'}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return <button onClick={handleExport}>Export {format.toUpperCase()}</button>;
}
```

---

## Database Transactions

### Explicit transaction management

```python
# repositories/base.py
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

class BaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    @asynccontextmanager
    async def transaction(self):
        """Explicit transaction — commits on exit, rolls back on exception."""
        async with self.session.begin():
            yield

# services/order_service.py
class OrderService:
    async def create_order(self, data: OrderCreate) -> Order:
        async with self.repo.transaction():
            # All operations in same transaction — all succeed or all fail
            order = await self.order_repo.create(Order(...))
            await self.inventory_repo.decrement(data.product_id, data.quantity)
            await self.billing_repo.charge(data.user_id, order.total)
            # If any of these raise → transaction rolls back automatically
        return order
```

### Savepoints — partial rollback

```python
# Useful for retrying part of a transaction
async def create_order_with_fallback(self, data: OrderCreate) -> Order:
    async with self.session.begin():
        order = await self.order_repo.create(Order(...))

        # Try premium shipping — fall back to standard if fails
        async with self.session.begin_nested() as savepoint:
            try:
                await self.shipping_repo.reserve_premium(order.id)
            except ShippingUnavailableError:
                await savepoint.rollback()
                await self.shipping_repo.reserve_standard(order.id)

        return order
```

---

## Data Factories / Seeding

Generate realistic test data — never manually create test objects.

```bash
pip install factory-boy faker
```

```python
# tests/factories.py
import factory
from factory.alchemy import SQLAlchemyModelFactory
from faker import Faker
from app.models.user import User
from app.models.post import Post
from app.core.security import hash_password
from ulid import ULID

fake = Faker()

class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "commit"

    public_id = factory.LazyFunction(lambda: str(ULID()))
    name = factory.LazyFunction(fake.name)
    email = factory.LazyFunction(fake.unique.email)
    hashed_password = factory.LazyFunction(lambda: hash_password("password123"))
    tenant_id = 1
    status = "active"

class AdminUserFactory(UserFactory):
    """Admin user — override only what's different."""
    role = "admin"

class PostFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Post
        sqlalchemy_session_persistence = "commit"

    public_id = factory.LazyFunction(lambda: str(ULID()))
    title = factory.LazyFunction(fake.sentence)
    body = factory.LazyFunction(fake.paragraphs(3))
    user = factory.SubFactory(UserFactory)   # auto-creates related user
    tenant_id = factory.SelfAttribute("user.tenant_id")

# Usage in tests
async def test_list_users(client, db_session):
    UserFactory._meta.sqlalchemy_session = db_session()

    users = UserFactory.create_batch(5)               # create 5 users
    admin = AdminUserFactory.create()                  # create 1 admin
    post = PostFactory.create(user=users[0])           # post owned by first user

    response = await client.get("/api/v1/users")
    assert response.status_code == 200
    assert len(response.json()["data"]) == 6
```

```python
# scripts/seed_db.py — for local dev
import asyncio
from app.db.session import AsyncSessionLocal
from tests.factories import UserFactory, PostFactory

async def seed():
    async with AsyncSessionLocal() as session:
        UserFactory._meta.sqlalchemy_session = session
        PostFactory._meta.sqlalchemy_session = session

        admin = AdminUserFactory.create(email="admin@example.com")
        users = UserFactory.create_batch(20)
        for user in users:
            PostFactory.create_batch(3, user=user)

        print(f"Seeded: 1 admin, {len(users)} users, {len(users) * 3} posts")

asyncio.run(seed())
```

---

## Scheduled / Cron Jobs

Recurring tasks — daily reports, cleanup, data sync.

```python
# workers/cron.py
from arq import cron
from arq.connections import RedisSettings

async def cleanup_expired_tokens(ctx):
    """Delete expired refresh tokens — run nightly."""
    db = ctx["db"]
    deleted = await db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(timezone.utc))
    )
    log.info("cleanup_expired_tokens", deleted=deleted.rowcount)

async def send_weekly_digest(ctx):
    """Send weekly email digest — run every Monday at 8am."""
    users = await ctx["user_repo"].get_digest_subscribers()
    for user in users:
        await ctx["email_service"].send_weekly_digest(user)
    log.info("weekly_digest_sent", count=len(users))

async def refresh_materialized_views(ctx):
    """Refresh expensive aggregations — run hourly."""
    await ctx["db"].execute("REFRESH MATERIALIZED VIEW CONCURRENTLY user_stats")
    log.info("materialized_views_refreshed")

# Worker config
class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [cleanup_expired_tokens, send_weekly_digest, refresh_materialized_views]
    cron_jobs = [
        cron(cleanup_expired_tokens, hour=2, minute=0),          # daily 2am
        cron(send_weekly_digest, weekday=0, hour=8, minute=0),   # Monday 8am
        cron(refresh_materialized_views, minute=0),               # every hour
    ]
    max_jobs = 10
    job_timeout = 300  # 5 minutes max per job
```

---

## Materialized Views

Pre-compute expensive aggregations — query result cached in a table, refreshed periodically.

```python
# Alembic migration
def upgrade():
    op.execute("""
        CREATE MATERIALIZED VIEW user_stats AS
        SELECT
            u.tenant_id,
            COUNT(u.id)                                          AS total_users,
            COUNT(u.id) FILTER (WHERE u.status = 'active')      AS active_users,
            COUNT(p.id)                                          AS total_posts,
            MAX(u.created_at)                                    AS last_signup_at
        FROM users u
        LEFT JOIN posts p ON p.user_id = u.id AND p.deleted_at IS NULL
        WHERE u.deleted_at IS NULL
        GROUP BY u.tenant_id;

        -- Index for fast tenant lookups
        CREATE UNIQUE INDEX ON user_stats (tenant_id);
    """)

def downgrade():
    op.execute("DROP MATERIALIZED VIEW IF EXISTS user_stats")
```

```python
# repositories/stats_repository.py
async def get_tenant_stats(self, tenant_id: int) -> dict:
    """Reads from materialized view — fast, never hits main tables."""
    result = await self.session.execute(
        text("SELECT * FROM user_stats WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else {}

# Refresh on-demand (also runs via cron — see above)
async def refresh_stats(self):
    await self.session.execute(
        text("REFRESH MATERIALIZED VIEW CONCURRENTLY user_stats")
        # CONCURRENTLY = no lock, readers can still query during refresh
    )
```
