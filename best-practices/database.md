# Database

## Indexing Strategy

### Types of Indexes

```python
# models/user.py
from sqlalchemy import Index, BigInteger, String, DateTime, Boolean
from sqlalchemy.orm import mapped_column, Mapped

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(26), unique=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Composite index — queries filtering by tenant + status together
        Index("ix_users_tenant_status", "tenant_id", "status"),

        # Partial index — only index active users (excludes deleted rows)
        Index(
            "ix_users_active",
            "tenant_id", "created_at",
            postgresql_where="deleted_at IS NULL",
        ),

        # Covering index — includes email so query never hits table
        Index(
            "ix_users_tenant_email",
            "tenant_id", "email",
            postgresql_include=["id", "public_id", "status"],
        ),
    )
```

### When to Add Each Index Type

| Index type | Use when |
|------------|----------|
| Single column | Frequently filtered/sorted alone |
| Composite | Multiple columns always filtered together — order matters (most selective first) |
| Partial | Most queries filter by a condition (e.g. `deleted_at IS NULL`) |
| Covering (`INCLUDE`) | Query selects a small set of columns — avoids heap fetch |
| BRIN | Time-series data (logs, events) — very small, good for append-only tables |

### EXPLAIN ANALYZE — Always Check Query Plans

```python
# Run this during development to catch slow queries
# Never skip this before deploying queries on large tables

# In psql or via SQLAlchemy:
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT u.id, u.email
FROM users u
WHERE u.tenant_id = 1
  AND u.deleted_at IS NULL
ORDER BY u.created_at DESC
LIMIT 20;

# Look for:
# ❌ Seq Scan       → missing index
# ❌ high rows      → rows estimate far from actual
# ✅ Index Scan     → index used
# ✅ Index Only Scan → covering index (fastest)
```

### Slow Query Logging

```python
# core/db.py — log queries slower than 200ms
from sqlalchemy import event
from sqlalchemy.engine import Engine
import time, structlog

log = structlog.get_logger()

@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_start_time", []).append(time.monotonic())

@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.monotonic() - conn.info["query_start_time"].pop()
    if total > 0.2:  # 200ms threshold
        log.warning("slow_query", duration_ms=round(total * 1000), query=statement[:200])
```

---

## Full-Text Search

### PostgreSQL (Default Choice)

Built-in, no extra infrastructure, good for most apps.

```python
# models/post.py
from sqlalchemy import Column, Index, func
from sqlalchemy.dialects.postgresql import TSVECTOR

class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    search_vector: Mapped[any] = mapped_column(
        TSVECTOR,
        nullable=True,
        comment="Auto-updated via trigger",
    )

    __table_args__ = (
        # GIN index for fast full-text search
        Index("ix_posts_search", "search_vector", postgresql_using="gin"),
    )
```

```python
# Alembic migration — trigger keeps search_vector up to date automatically
def upgrade():
    op.execute("""
        ALTER TABLE posts ADD COLUMN search_vector tsvector;

        CREATE INDEX ix_posts_search ON posts USING gin(search_vector);

        -- Auto-update trigger
        CREATE FUNCTION posts_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.body, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER posts_search_vector_trigger
        BEFORE INSERT OR UPDATE ON posts
        FOR EACH ROW EXECUTE FUNCTION posts_search_vector_update();

        -- Backfill existing rows
        UPDATE posts SET search_vector =
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(body, '')), 'B');
    """)
```

```python
# repositories/post_repository.py
from sqlalchemy import select, func, text

class PostRepository:
    async def search(
        self,
        query: str,
        tenant_id: int,
        limit: int = 20,
        cursor: int | None = None,
    ) -> list[Post]:
        ts_query = func.plainto_tsquery("english", query)

        stmt = (
            select(Post, func.ts_rank(Post.search_vector, ts_query).label("rank"))
            .where(
                Post.tenant_id == tenant_id,
                Post.deleted_at.is_(None),
                Post.search_vector.op("@@")(ts_query),
            )
            .order_by(text("rank DESC"), Post.id.desc())
            .limit(limit)
        )
        if cursor:
            stmt = stmt.where(Post.id < cursor)

        result = await self.session.execute(stmt)
        return [row.Post for row in result]
```

```python
# api/v1/endpoints/search.py
@router.get("/search")
async def search(
    q: str = Query(..., min_length=2),
    cursor: int | None = None,
    service: PostService = Depends(get_post_service),
):
    if not q.strip():
        raise AppValidationError("Search query cannot be empty")
    return await service.search(q, cursor=cursor)
```

### When to Use Elasticsearch Instead

| Scenario | PostgreSQL FTS | Elasticsearch |
|----------|---------------|---------------|
| < 10M records | ✅ | Overkill |
| Fuzzy matching ("helllo" → "hello") | ❌ | ✅ |
| Typo tolerance | ❌ | ✅ |
| Multi-language stemming | Limited | ✅ |
| Faceted search (filters + counts) | Slow | ✅ |
| > 50M records | Slow | ✅ |

**Rule:** Start with PostgreSQL. Migrate to Elasticsearch only when you hit its limits.
