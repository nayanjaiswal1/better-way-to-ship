# Optimized API Patterns

## The Problem With Naive SDUI

Without optimization, server-driven UI causes too many calls:

```
App start:
  GET /api/v1/users/me       → current user
  GET /api/v1/flags          → feature flags
  GET /api/meta/navigation   → sidebar

Every page load:
  GET /api/v1/users          → data + filters + columns + permissions + actions
                               (meta is identical every time — wasted bandwidth)
```

**Solution: 3 rules**
1. **Bootstrap** — merge all app-startup calls into one
2. **Separate schema from data** — meta cached long, data cached short
3. **Parallel fetch** — schema + data fetched simultaneously, not waterfall

---

## Rule 1: Bootstrap Endpoint

One call on app start instead of three.

### Backend

```python
# api/v1/endpoints/bootstrap.py
from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_user
from app.services.flag_service import get_flags_for_user
from app.services.nav_service import get_navigation_for_user

router = APIRouter()

@router.get("/bootstrap")
async def bootstrap(current_user=Depends(get_current_user)):
    """Single call to hydrate the app on startup."""
    flags, navigation = await asyncio.gather(
        get_flags_for_user(current_user.id, current_user.tenant_id),
        get_navigation_for_user(current_user.id, current_user.tenant_id),
    )
    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "tenant_id": current_user.tenant_id,
        },
        "flags": flags,           # { "new-dashboard": True, "bulk-export": False }
        "navigation": navigation, # [{ key, label, path, icon, children }]
    }
```

### React — fetch once, seed all caches

```tsx
// hooks/useBootstrap.ts
import { useQuery, useQueryClient } from '@tanstack/react-query';

export function useBootstrap() {
  const queryClient = useQueryClient();

  return useQuery({
    queryKey: ['bootstrap'],
    queryFn: async () => {
      const data = await fetch('/api/v1/bootstrap', {
        credentials: 'include',
      }).then(r => r.json());

      // Seed individual caches — other hooks read from these
      queryClient.setQueryData(['currentUser'], data.user);
      queryClient.setQueryData(['flags'], data.flags);
      queryClient.setQueryData(['navigation'], data.navigation);

      return data;
    },
    staleTime: 1000 * 60 * 10,   // 10 minutes
    retry: false,
  });
}

// App.tsx — call once at root
function App() {
  const { isLoading } = useBootstrap();
  if (isLoading) return <AppSkeleton />;
  return <Router />;
}
```

---

## Rule 2: Separate Schema from Data

Meta (columns, filters, actions, permissions) changes rarely.
Data changes often. Cache them differently.

```
❌ Before — meta repeated every request:
  GET /api/v1/users → { data: [...], meta: { filters, columns, actions, permissions, pagination } }

✅ After — split into two endpoints:
  GET /api/v1/users/schema  → { filters, columns, actions, permissions }  ← cached 30 min
  GET /api/v1/users         → { data: [...], pagination }                  ← cached 5 min
```

### Backend

```python
# api/v1/endpoints/users.py
from fastapi import APIRouter, Depends
from app.schemas.common import ResourceSchema, APIResponse, PaginationMeta

router = APIRouter()

@router.get("/schema", response_model=ResourceSchema)
async def users_schema(current_user=Depends(get_current_user)):
    """Static metadata for the users resource. Cached aggressively."""
    return ResourceSchema(
        filters=[
            FilterDef(field="name", type="text", label="Name"),
            FilterDef(field="status", type="select", label="Status",
                      options=[{"value": "active", "label": "Active"},
                               {"value": "inactive", "label": "Inactive"}]),
        ],
        columns=[
            ColumnDef(field="name", label="Name", sortable=True),
            ColumnDef(field="status", label="Status", render="badge",
                      render_options={"active": "green", "inactive": "red"}),
            ColumnDef(field="email", label="Email"),
        ],
        actions=[
            ActionDef(key="delete", label="Delete", variant="danger",
                      bulk=True, confirm="Delete selected users?"),
            ActionDef(key="export", label="Export", bulk=True),
        ],
        permissions=await get_permissions_for_user(current_user, "users"),
    )

@router.get("/", response_model=APIResponse[list[UserResponse]])
async def list_users(
    cursor: str | None = None,
    limit: int = 20,
    service: UserService = Depends(get_user_service),
):
    """Data only — no schema meta here."""
    users = await service.list_users(cursor=cursor, limit=limit)
    return APIResponse(
        data=users.items,
        meta=ResponseMeta(
            pagination=PaginationMeta(
                total=users.total,
                next_cursor=users.next_cursor,
                limit=limit,
            )
        ),
    )
```

### React — different staleTime per concern

```tsx
// hooks/useResource.ts
import { useQueries } from '@tanstack/react-query';

const SCHEMA_STALE = 1000 * 60 * 30   // 30 minutes — rarely changes
const DATA_STALE   = 1000 * 60 * 5    // 5 minutes — changes often

export function useResource(resource: string, params?: Record<string, any>) {
  // Fetch schema + data in PARALLEL — no waterfall
  const [schema, data] = useQueries({
    queries: [
      {
        queryKey: [resource, 'schema'],
        queryFn: () =>
          fetch(`/api/v1/${resource}/schema`, { credentials: 'include' }).then(r => r.json()),
        staleTime: SCHEMA_STALE,
      },
      {
        queryKey: [resource, 'data', params],
        queryFn: () =>
          fetch(`/api/v1/${resource}?${new URLSearchParams(params)}`, {
            credentials: 'include',
          }).then(r => r.json()),
        staleTime: DATA_STALE,
      },
    ],
  });

  return {
    schema: schema.data,
    data: data.data?.data,
    pagination: data.data?.meta?.pagination,
    isLoading: schema.isLoading || data.isLoading,
  };
}

// Usage — entire page driven by one hook
function UsersPage() {
  const { schema, data, pagination } = useResource('users');

  return (
    <>
      <FilterBar filters={schema?.filters} />
      <ActionBar actions={schema?.actions} />
      <DataTable columns={schema?.columns} rows={data} />
      <Pagination meta={pagination} />
    </>
  );
}
```

---

## Rule 3: Cache Hierarchy

Different data has different freshness requirements:

```
Bootstrap (user, flags, nav)  → staleTime: 10 min  — changes on login/logout
Resource schema               → staleTime: 30 min  — changes on deploy
Resource data                 → staleTime: 5 min   — changes on user action
Detail view                   → staleTime: 2 min   — more specific, staler faster
```

### Global queryClient defaults

```tsx
// main.tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,    // 5 min default
      gcTime: 1000 * 60 * 30,      // 30 min gc
      retry: 3,
      refetchOnWindowFocus: false,
    },
  },
});
```

---

## Prefetching on Navigation

Prefetch schema + data together before the user navigates:

```tsx
function NavLink({ to, resource }: { to: string; resource: string }) {
  const queryClient = useQueryClient();

  const prefetch = () => {
    // Prefetch both schema and data in parallel
    queryClient.prefetchQuery({
      queryKey: [resource, 'schema'],
      queryFn: () =>
        fetch(`/api/v1/${resource}/schema`, { credentials: 'include' }).then(r => r.json()),
      staleTime: 1000 * 60 * 30,
    });
    queryClient.prefetchQuery({
      queryKey: [resource, 'data', {}],
      queryFn: () =>
        fetch(`/api/v1/${resource}`, { credentials: 'include' }).then(r => r.json()),
      staleTime: 1000 * 60 * 5,
    });
  };

  return (
    <Link to={to} onMouseEnter={prefetch}>
      {resource}
    </Link>
  );
}
```

---

## Infinite Scroll

```tsx
function ResourceList({ resource }: { resource: string }) {
  const observerRef = useRef<IntersectionObserver>();

  const { data, hasNextPage, fetchNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: [resource, 'infinite'],
    queryFn: ({ pageParam }) =>
      fetch(`/api/v1/${resource}?cursor=${pageParam ?? ''}`, {
        credentials: 'include',
      }).then(r => r.json()),
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.meta?.pagination?.next_cursor,
    staleTime: 1000 * 60 * 5,
  });

  const lastRef = useCallback((node: HTMLElement | null) => {
    if (observerRef.current) observerRef.current.disconnect();
    observerRef.current = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    });
    if (node) observerRef.current.observe(node);
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  return <div ref={lastRef}>{/* render rows */}</div>;
}
```

---

## ETags — Conditional Requests

Server returns an `ETag` (hash of response). Client sends it back. If nothing changed, server returns `304 Not Modified` — **zero bytes transferred**. Perfect for schema endpoints.

### Backend

```python
# core/etag.py
import hashlib, json
from fastapi import Request
from fastapi.responses import Response

def make_etag(data: any) -> str:
    return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()

def etag_response(request: Request, response: Response, data: any):
    etag = f'"{make_etag(data)}"'
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"

    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304)  # Not Modified — no body sent
    return data

# api/v1/endpoints/users.py
@router.get("/schema")
async def users_schema(request: Request, response: Response, ...):
    schema = await build_users_schema(current_user)
    return etag_response(request, response, schema)
```

### React — automatic via fetch + React Query

```tsx
// lib/fetchWithEtag.ts
const etagCache = new Map<string, string>();

export async function fetchWithEtag(url: string) {
  const headers: HeadersInit = { credentials: 'include' } as any;
  const cached = etagCache.get(url);

  if (cached) headers['If-None-Match'] = cached;

  const res = await fetch(url, { headers, credentials: 'include' });

  if (res.status === 304) {
    // Not modified — return cached data
    return null;  // React Query keeps previous data
  }

  const etag = res.headers.get('ETag');
  if (etag) etagCache.set(url, etag);

  return res.json();
}
```

---

## Field Selection

Client requests only the fields it needs — reduces payload, especially for list views.

### Backend

```python
# schemas/common.py
from fastapi import Query

def parse_fields(fields: str | None = Query(None)) -> set[str] | None:
    """?fields=id,name,email → {'id', 'name', 'email'}"""
    return set(fields.split(',')) if fields else None

# api/v1/endpoints/users.py
@router.get("/")
async def list_users(
    fields: set[str] | None = Depends(parse_fields),
    service: UserService = Depends(get_user_service),
):
    users = await service.list_users()
    if fields:
        return [
            {k: v for k, v in u.model_dump().items() if k in fields}
            for u in users
        ]
    return users
```

### React — request only what each view needs

```tsx
// List view — only needs id, name, status
const { data } = useQuery({
  queryKey: ['users', 'list'],
  queryFn: () =>
    fetch('/api/v1/users?fields=id,name,status,email', {
      credentials: 'include',
    }).then(r => r.json()),
});

// Detail view — needs everything
const { data } = useQuery({
  queryKey: ['users', id],
  queryFn: () =>
    fetch(`/api/v1/users/${id}`, { credentials: 'include' }).then(r => r.json()),
});
```

---

## Idempotency Keys

Safe to retry mutations without duplicating side effects. Critical for payments, order creation, emails.

### Backend

```python
# core/idempotency.py
import redis.asyncio as redis
from fastapi import Header, HTTPException
import json

async def check_idempotency(
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    redis_client: redis.Redis = Depends(get_redis),
):
    if not idempotency_key:
        return None  # optional for non-critical endpoints

    cached = await redis_client.get(f"idempotency:{idempotency_key}")
    if cached:
        raise HTTPException(status_code=200, detail=json.loads(cached))  # return cached result

    return idempotency_key

async def store_idempotency(
    key: str,
    result: dict,
    redis_client: redis.Redis,
    ttl: int = 86400,  # 24 hours
):
    await redis_client.setex(
        f"idempotency:{key}",
        ttl,
        json.dumps(result),
    )

# api/v1/endpoints/orders.py
@router.post("/orders")
async def create_order(
    data: OrderCreate,
    idempotency_key: str | None = Depends(check_idempotency),
    service: OrderService = Depends(get_order_service),
):
    result = await service.create_order(data)

    if idempotency_key:
        await store_idempotency(idempotency_key, result.model_dump(), redis_client)

    return result
```

### React — generate key per user action

```tsx
import { v4 as uuidv4 } from 'uuid';

export function useCreateOrder() {
  return useMutation({
    mutationFn: (data: OrderCreate) => {
      // New UUID per submission — same key on retry
      const key = uuidv4();
      return fetch('/api/v1/orders', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': key,   // safe to retry with same key
        },
        body: JSON.stringify(data),
      }).then(r => r.json());
    },
  });
}
```

---

## Summary — API Call Budget

| Call | When | Cached |
|------|------|--------|
| `GET /api/v1/bootstrap` | App start, once | 10 min |
| `GET /api/v1/{resource}/schema` | First visit to resource | 30 min |
| `GET /api/v1/{resource}` | Every data refresh | 5 min |
| `GET /api/v1/{resource}/{id}` | Detail view | 2 min |

A user visiting 3 pages makes **4-6 total API calls** instead of 10+.
