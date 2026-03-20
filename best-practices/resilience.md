# Resilience Patterns

Production systems fail. These patterns keep your app working when they do.

---

## Exponential Backoff Retry

Retry failed requests with increasing delay — avoids hammering a struggling service.

### React — React Query built-in retry

```tsx
// main.tsx — configure globally
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30000),
      // attempt 1 → 2s, attempt 2 → 4s, attempt 3 → 8s, max 30s
    },
    mutations: {
      retry: 1,  // retry mutations once only — idempotency required
    },
  },
});
```

### Backend — retry for external service calls

```python
# core/retry.py
import asyncio
from functools import wraps

def with_retry(max_attempts: int = 3, base_delay: float = 1.0):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s
                        await asyncio.sleep(delay)
            raise last_error
        return wrapper
    return decorator

# Usage — wrap external service calls
@with_retry(max_attempts=3, base_delay=1.0)
async def send_email(to: str, subject: str, body: str):
    await email_client.send(to=to, subject=subject, body=body)
```

---

## Circuit Breaker

Stop calling a failing service — fail fast instead of queuing up timeouts.

```
CLOSED (normal) → too many failures → OPEN (fail fast)
OPEN → after timeout → HALF-OPEN (test one request)
HALF-OPEN → success → CLOSED | failure → OPEN
```

```python
# core/circuit_breaker.py
import asyncio
from enum import Enum
from datetime import datetime, timedelta

class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,  # seconds
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = State.CLOSED
        self.opened_at: datetime | None = None

    async def call(self, fn, *args, **kwargs):
        if self.state == State.OPEN:
            if datetime.now() - self.opened_at > timedelta(seconds=self.recovery_timeout):
                self.state = State.HALF_OPEN
            else:
                raise ServiceUnavailableError("Circuit is open — service unavailable")

        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        self.failure_count = 0
        self.state = State.CLOSED

    def _on_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = State.OPEN
            self.opened_at = datetime.now()

# Usage — wrap calls to external services
payment_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

async def charge_card(amount: float, card_token: str):
    return await payment_breaker.call(
        payment_gateway.charge, amount=amount, token=card_token
    )
```

---

## Timeout Strategy

Different operations need different timeouts — don't use one global timeout.

```python
# core/config.py
class TimeoutSettings(BaseSettings):
    # Fast operations
    db_read_timeout: int = 5       # seconds
    cache_timeout: int = 2

    # Slower operations
    db_write_timeout: int = 10
    external_api_timeout: int = 15

    # Long running
    report_generation_timeout: int = 120
    file_upload_timeout: int = 300

settings = TimeoutSettings()

# Usage with httpx for external calls
import httpx

async def call_external_api(url: str, data: dict):
    async with httpx.AsyncClient(timeout=settings.external_api_timeout) as client:
        response = await client.post(url, json=data)
        response.raise_for_status()
        return response.json()
```

```tsx
// React — AbortController for request cancellation
function useUserData(userId: number) {
  return useQuery({
    queryKey: ['users', userId],
    queryFn: async ({ signal }) => {
      // signal is automatically passed by React Query — cancels on unmount
      const res = await fetch(`/api/v1/users/${userId}`, {
        credentials: 'include',
        signal,  // cancel if component unmounts or queryKey changes
      });
      if (!res.ok) throw new Error('Failed to fetch');
      return res.json();
    },
  });
}
```

---

## Graceful Degradation

Show something useful when parts of the system are down — never a blank page.

### React — per-section error boundaries with fallbacks

```tsx
// components/DegradedSection.tsx
interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  name: string;  // for logging
}

export function DegradedSection({ children, fallback, name }: Props) {
  return (
    <ErrorBoundary
      fallback={
        fallback ?? (
          <div className="degraded-notice">
            <p>{name} is temporarily unavailable.</p>
            <button onClick={() => window.location.reload()}>Retry</button>
          </div>
        )
      }
    >
      {children}
    </ErrorBoundary>
  );
}

// Usage — each section degrades independently
function Dashboard() {
  return (
    <div>
      <DegradedSection name="Analytics">
        <AnalyticsWidget />       {/* if this crashes, rest of page still works */}
      </DegradedSection>

      <DegradedSection name="Activity Feed">
        <ActivityFeed />
      </DegradedSection>
    </div>
  );
}
```

### React — stale data with visual indicator

```tsx
// Show stale data with a warning instead of blank screen
function UserTable() {
  const { data, isStale, isFetching } = useQuery({
    queryKey: ['users', 'data'],
    queryFn: fetchUsers,
    staleTime: 1000 * 60 * 5,
  });

  return (
    <>
      {isStale && !isFetching && (
        <Banner variant="warning">
          Showing cached data — live data unavailable. <RefetchButton />
        </Banner>
      )}
      <DataTable columns={schema?.columns} rows={data} />
    </>
  );
}
```

### Backend — health check endpoint

```python
# api/v1/endpoints/health.py
from fastapi import APIRouter
from app.db.session import get_db
import redis.asyncio as redis

router = APIRouter()

@router.get("/health")
async def health_check(db=Depends(get_db), redis_client=Depends(get_redis)):
    status = {"status": "ok", "services": {}}

    # Check database
    try:
        await db.execute("SELECT 1")
        status["services"]["database"] = "ok"
    except Exception:
        status["services"]["database"] = "degraded"
        status["status"] = "degraded"

    # Check Redis
    try:
        await redis_client.ping()
        status["services"]["redis"] = "ok"
    except Exception:
        status["services"]["redis"] = "degraded"
        status["status"] = "degraded"

    return status

# Response:
# { "status": "degraded", "services": { "database": "ok", "redis": "degraded" } }
```

---

## API Rate Limiting Strategy

Different limits per endpoint type — not one global limit.

```python
# core/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# main.py
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# api/v1/endpoints/auth.py
@router.post("/login")
@limiter.limit("5/minute")            # brute force protection
async def login(request: Request, ...): ...

# api/v1/endpoints/bootstrap.py
@router.get("/bootstrap")
@limiter.limit("10/minute")           # startup only
async def bootstrap(request: Request, ...): ...

# api/v1/endpoints/users.py
@router.get("/schema")
@limiter.limit("30/minute")           # rarely changes
async def users_schema(request: Request, ...): ...

@router.get("/")
@limiter.limit("100/minute")          # normal usage
async def list_users(request: Request, ...): ...

# api/v1/endpoints/ai.py
@router.post("/ai/generate")
@limiter.limit("10/minute")           # expensive — protect costs
async def generate(request: Request, ...): ...
```

```
Endpoint type          Limit        Reason
/auth/login            5/min        Brute force protection
/bootstrap             10/min       App startup only
/*/schema              30/min       Rarely changes
/* (general)           100/min      Normal usage
/ai/*                  10/min       Expensive operations
```
