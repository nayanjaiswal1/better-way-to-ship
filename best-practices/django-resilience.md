# Django Resilience — Rate Limiting, Throttling, Circuit Breaker

## DRF Throttling — Built-In

```python
# config/settings/base.py
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/hour",
        "user": "1000/hour",
    },
}

# Uses cache backend — set to Redis (not locmem in production)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
    }
}
```

### Custom Throttle Classes per Endpoint Type

```python
# common/throttling.py
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

class LoginThrottle(AnonRateThrottle):
    """5 login attempts per minute per IP."""
    scope = "login"
    rate  = "5/min"

class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"
    rate  = "3/hour"

class ExportThrottle(UserRateThrottle):
    """Expensive — limit export requests."""
    scope = "export"
    rate  = "10/hour"

class AIThrottle(UserRateThrottle):
    """LLM calls — expensive and rate-limited upstream."""
    scope = "ai"
    rate  = "50/hour"

class PublicReadThrottle(AnonRateThrottle):
    scope = "public_read"
    rate  = "120/min"

class BurstThrottle(UserRateThrottle):
    """Short burst limit — prevent abuse spikes."""
    scope = "burst"
    rate  = "30/min"
```

```python
# Apply per-view
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes   = [LoginThrottle]

class ExportView(APIView):
    throttle_classes = [ExportThrottle, BurstThrottle]

class AICompletionView(APIView):
    throttle_classes = [AIThrottle]

# Or per-action in ViewSets
class UserViewSet(viewsets.ModelViewSet):
    def get_throttles(self):
        if self.action == "export":
            return [ExportThrottle()]
        return super().get_throttles()
```

---

## Tenant-Based Rate Limiting

Different limits per plan tier.

```python
# common/throttling.py
from rest_framework.throttling import BaseThrottle
from django.core.cache import cache

PLAN_LIMITS = {
    "free":       {"api_calls": "100/hour"},
    "pro":        {"api_calls": "5000/hour"},
    "enterprise": {"api_calls": "50000/hour"},
}

class TenantRateThrottle(BaseThrottle):
    """Rate limit based on tenant plan."""

    def get_cache_key(self, request, view):
        if not request.user.is_authenticated:
            return None
        return f"throttle:tenant:{request.user.tenant_id}:api_calls"

    def allow_request(self, request, view):
        if not request.user.is_authenticated:
            return True

        key = self.get_cache_key(request, view)
        plan = request.user.tenant.plan
        rate_str = PLAN_LIMITS.get(plan, {}).get("api_calls", "1000/hour")
        limit, period = self._parse_rate(rate_str)

        count = cache.get(key, 0)
        if count >= limit:
            self.wait_value = period
            return False

        # Increment with TTL
        pipe = cache.client.get_client().pipeline()
        pipe.incr(key)
        pipe.expire(key, period)
        pipe.execute()
        return True

    def _parse_rate(self, rate: str) -> tuple[int, int]:
        count, period = rate.split("/")
        periods = {"min": 60, "hour": 3600, "day": 86400}
        return int(count), periods[period]

    def wait(self):
        return self.wait_value
```

---

## django-ratelimit — View-Level Decorator

For non-DRF views or more granular control.

```bash
pip install django-ratelimit
```

```python
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from django.http import JsonResponse

# Function-based view
@ratelimit(key="ip", rate="5/m", method="POST", block=True)
def login_view(request):
    ...

# Class-based view
class LoginView(APIView):
    @method_decorator(ratelimit(key="ip", rate="5/m", block=True))
    def post(self, request):
        ...

# Custom 429 handler
def ratelimited_error(request, exception):
    return JsonResponse(
        {"error": {"code": "rate_limited", "message": "Too many requests", "status": 429}},
        status=429,
    )

# config/urls.py
handler429 = "common.views.ratelimited_error"
```

---

## Exponential Backoff — Outbound HTTP

```python
# common/http.py
import httpx
import time
from typing import Any

def request_with_backoff(
    method: str,
    url: str,
    max_retries: int = 3,
    **kwargs: Any,
) -> httpx.Response:
    """HTTP request with exponential backoff for transient failures."""
    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=10) as client:
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            is_retryable = (
                isinstance(exc, httpx.TransportError)
                or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 502, 503, 504))
            )
            if not is_retryable or attempt == max_retries:
                raise

            delay = min(2 ** attempt + (0.1 * attempt), 60)
            time.sleep(delay)
```

---

## Circuit Breaker

```python
# common/circuit_breaker.py
import time
from django.core.cache import cache
from enum import StrEnum

class State(StrEnum):
    CLOSED    = "closed"      # normal — requests pass through
    OPEN      = "open"        # failing — requests blocked
    HALF_OPEN = "half_open"   # testing — one request allowed

class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
    ):
        self.name              = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self.success_threshold = success_threshold

    def _key(self, suffix: str) -> str:
        return f"circuit_breaker:{self.name}:{suffix}"

    @property
    def state(self) -> State:
        raw = cache.get(self._key("state"), State.CLOSED)
        return State(raw)

    def call(self, func, *args, **kwargs):
        state = self.state

        if state == State.OPEN:
            opened_at = cache.get(self._key("opened_at"), 0)
            if time.time() - opened_at > self.recovery_timeout:
                cache.set(self._key("state"), State.HALF_OPEN)
            else:
                raise Exception(f"Circuit {self.name} is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise

    def _on_success(self):
        if self.state == State.HALF_OPEN:
            successes = cache.incr(self._key("successes"), 1)
            if successes >= self.success_threshold:
                cache.set(self._key("state"), State.CLOSED)
                cache.delete(self._key("failures"))
                cache.delete(self._key("successes"))
        else:
            cache.delete(self._key("failures"))

    def _on_failure(self):
        failures = cache.incr(self._key("failures"), 1)
        if failures >= self.failure_threshold:
            cache.set(self._key("state"), State.OPEN)
            cache.set(self._key("opened_at"), time.time())
            cache.delete(self._key("failures"))

# Usage
stripe_breaker  = CircuitBreaker("stripe", failure_threshold=5, recovery_timeout=60)
sendgrid_breaker = CircuitBreaker("sendgrid", failure_threshold=3, recovery_timeout=120)

def charge_card(amount, token):
    return stripe_breaker.call(_do_stripe_charge, amount, token)
```

---

## Timeouts — Per Operation Type

```python
# common/http.py
import httpx

# Different timeouts per operation type
TIMEOUTS = {
    "default":  httpx.Timeout(10.0),
    "payment":  httpx.Timeout(30.0),   # payment APIs can be slow
    "email":    httpx.Timeout(5.0),
    "webhook":  httpx.Timeout(10.0),
    "ai":       httpx.Timeout(60.0),   # LLM streaming
}

def get_client(operation: str = "default") -> httpx.Client:
    return httpx.Client(timeout=TIMEOUTS.get(operation, TIMEOUTS["default"]))
```

```python
# Django ORM query timeout — prevent runaway queries
from django.db import connection

def set_statement_timeout(ms: int = 5000):
    """Set PostgreSQL statement timeout for this connection."""
    with connection.cursor() as cursor:
        cursor.execute(f"SET statement_timeout = {ms}")

# Use in expensive endpoints
class ReportView(APIView):
    def get(self, request):
        set_statement_timeout(10000)  # 10s max for reports
        data = ReportService.generate(request.user.tenant)
        return Response(data)
```

---

## Graceful Degradation

```python
# common/fallbacks.py
import structlog
from functools import wraps
from typing import TypeVar, Callable, Any

logger = structlog.get_logger()

T = TypeVar("T")

def with_fallback(fallback_value, log_level="warning"):
    """Return fallback instead of raising on failure."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                getattr(logger, log_level)(
                    "fallback_triggered",
                    func=func.__name__,
                    error=str(exc),
                )
                return fallback_value
        return wrapper
    return decorator

# Usage
@with_fallback(fallback_value=[], log_level="warning")
def get_recommendations(user):
    return RecommendationService.get(user)

@with_fallback(fallback_value={"flags": {}})
def get_feature_flags(tenant):
    return FeatureFlagService.get_all(tenant)
```

---

## Health Check with Dependency Status

```python
# common/views.py
import time
from django.db import connection
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        checks = {}
        start  = time.monotonic()

        # Database
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["database"] = {"status": "ok", "latency_ms": round((time.monotonic() - start) * 1000)}
        except Exception as e:
            checks["database"] = {"status": "error", "error": str(e)}

        # Cache / Redis
        try:
            t = time.monotonic()
            cache.set("health", "ok", 5)
            cache.get("health")
            checks["cache"] = {"status": "ok", "latency_ms": round((time.monotonic() - t) * 1000)}
        except Exception as e:
            checks["cache"] = {"status": "error", "error": str(e)}

        # Celery (check if workers are alive)
        try:
            from config.celery import app as celery_app
            inspect = celery_app.control.inspect(timeout=1)
            workers = inspect.ping()
            checks["celery"] = {"status": "ok" if workers else "degraded", "workers": len(workers or {})}
        except Exception as e:
            checks["celery"] = {"status": "error", "error": str(e)}

        all_ok = all(c.get("status") == "ok" for c in checks.values())
        return Response(
            {"status": "ok" if all_ok else "degraded", "checks": checks},
            status=200 if all_ok else 503,
        )
```

---

## Resilience Checklist

- [ ] `AnonRateThrottle` + `UserRateThrottle` as global defaults in DRF settings
- [ ] Custom throttle classes per endpoint type (login: 5/min, export: 10/hr, AI: 50/hr)
- [ ] Tenant-based rate limits tied to plan tier
- [ ] Circuit breaker on all external services (Stripe, SendGrid, etc.)
- [ ] Timeouts set per operation type — never default infinite timeout
- [ ] PostgreSQL `statement_timeout` on expensive queries
- [ ] `with_fallback` decorator on non-critical services
- [ ] Health check returns 503 if DB or cache is down
- [ ] Exponential backoff on outbound HTTP (Celery tasks)
- [ ] 429 returns `Retry-After` header — DRF does this automatically
