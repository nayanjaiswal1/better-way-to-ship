# Microservices

Start as a monolith. Extract services only when a specific boundary causes pain: deployment coupling, scaling bottleneck, team ownership conflict, or tech mismatch.

## When to Extract a Service

| Signal | Example |
|--------|---------|
| Independent scaling need | Video transcoding pegs CPU, rest of app is fine |
| Different deployment cadence | ML model updates hourly, core app deploys weekly |
| Team ownership boundary | Billing team owns billing service end-to-end |
| Technology mismatch | Need Rust for low-latency, Python for rest |
| Fault isolation | Payment failures must not crash user dashboard |

**Don't extract because**: "microservices are modern", under 50 engineers, or the monolith is fast enough.

---

## Service Communication

### Synchronous — HTTP/REST (service-to-service)

```python
# common/service_client.py — typed HTTP client for internal services
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

class ServiceClient:
    def __init__(self, base_url: str, service_name: str):
        self.base_url     = base_url
        self.service_name = service_name
        self._client      = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(5.0),
            headers={"X-Service-Name": "api-service"},
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def get(self, path: str, **kwargs) -> dict:
        response = await self._client.get(path, **kwargs)
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def post(self, path: str, **kwargs) -> dict:
        response = await self._client.post(path, **kwargs)
        response.raise_for_status()
        return response.json()

# Dependency injection
def get_billing_client() -> ServiceClient:
    return ServiceClient(
        base_url=settings.BILLING_SERVICE_URL,
        service_name="billing-service",
    )

# Usage in FastAPI
@router.post("/subscriptions")
async def create_subscription(
    body: SubscriptionCreate,
    billing: ServiceClient = Depends(get_billing_client),
    current_user: User = Depends(get_current_user),
):
    result = await billing.post("/subscriptions", json={
        "tenant_id": current_user.tenant_id,
        "plan": body.plan,
    })
    return result
```

### Asynchronous — Message Queue (event-driven)

Use async messaging for operations that don't need an immediate response.

```python
# core/messaging.py — publish/subscribe via Redis Streams
import redis.asyncio as redis
import json

class MessageBus:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)

    async def publish(self, stream: str, event_type: str, payload: dict) -> None:
        await self.redis.xadd(stream, {
            "event_type": event_type,
            "payload":    json.dumps(payload),
            "service":    settings.SERVICE_NAME,
        })

    async def subscribe(self, stream: str, group: str, consumer: str):
        """Yield messages from a Redis Stream consumer group."""
        try:
            await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception:
            pass  # group already exists

        while True:
            messages = await self.redis.xreadgroup(
                group, consumer, {stream: ">"}, count=10, block=1000
            )
            for _, msgs in messages:
                for msg_id, data in msgs:
                    yield msg_id, data
                    await self.redis.xack(stream, group, msg_id)

# Publisher (billing-service)
async def on_subscription_created(subscription):
    bus = MessageBus(settings.REDIS_URL)
    await bus.publish(
        stream="billing.events",
        event_type="subscription.created",
        payload={
            "tenant_id":   subscription.tenant_id,
            "plan":        subscription.plan,
            "activated_at": subscription.created_at.isoformat(),
        },
    )

# Consumer (api-service — reacts to billing events)
async def consume_billing_events():
    bus = MessageBus(settings.REDIS_URL)
    async for msg_id, data in bus.subscribe("billing.events", "api-service", "worker-1"):
        event_type = data[b"event_type"].decode()
        payload    = json.loads(data[b"payload"])

        if event_type == "subscription.created":
            await handle_subscription_created(payload)
```

---

## Service Discovery — Kubernetes DNS

In Kubernetes, services find each other via DNS. No service registry needed.

```yaml
# k8s/services.yaml
# Each service gets a stable DNS name: <service-name>.<namespace>.svc.cluster.local

apiVersion: v1
kind: Service
metadata:
  name: billing-service
  namespace: production
spec:
  selector:
    app: billing-service
  ports:
    - port: 80
      targetPort: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: notification-service
  namespace: production
spec:
  selector:
    app: notification-service
  ports:
    - port: 80
      targetPort: 8000
```

```python
# config/settings.py — service URLs via env vars (injected by K8s)
BILLING_SERVICE_URL      = env("BILLING_SERVICE_URL",      default="http://billing-service.production")
NOTIFICATION_SERVICE_URL = env("NOTIFICATION_SERVICE_URL", default="http://notification-service.production")
```

---

## API Gateway — Kong / Nginx

Single entry point for all services. Handles auth, rate limiting, routing.

```yaml
# k8s/ingress.yaml — nginx routes by path prefix
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-gateway
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /api/v1/billing(/|$)(.*)
            pathType: Prefix
            backend:
              service:
                name: billing-service
                port:
                  number: 80

          - path: /api/v1/notifications(/|$)(.*)
            pathType: Prefix
            backend:
              service:
                name: notification-service
                port:
                  number: 80

          - path: /api/v1(/|$)(.*)
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 80
```

---

## Service-to-Service Authentication

Services must authenticate to each other — never trust internal requests blindly.

```python
# core/service_auth.py — shared secret / JWT for service-to-service
import jwt
from fastapi import Header, HTTPException

SERVICE_TOKENS = {
    "billing-service":      settings.BILLING_SERVICE_TOKEN,
    "notification-service": settings.NOTIFICATION_SERVICE_TOKEN,
}

def get_service_token(service_name: str) -> str:
    return jwt.encode(
        {"service": service_name, "exp": time.time() + 3600},
        settings.SERVICE_JWT_SECRET,
        algorithm="HS256",
    )

async def verify_service_token(x_service_token: str = Header(...)) -> str:
    try:
        payload = jwt.decode(x_service_token, settings.SERVICE_JWT_SECRET, algorithms=["HS256"])
        return payload["service"]
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid service token")

# Usage — internal endpoint only callable by other services
@router.post("/internal/subscriptions/activate")
async def activate_subscription(
    body: ActivateRequest,
    calling_service: str = Depends(verify_service_token),
):
    # Only billing-service should call this
    if calling_service != "billing-service":
        raise HTTPException(status_code=403)
    ...
```

---

## Distributed Tracing — OpenTelemetry

Trace a request across multiple services.

```python
# core/tracing.py — same setup as observability.md, but propagate context
from opentelemetry.propagate import inject, extract
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

# Outbound — inject trace context into headers
class TracingServiceClient(ServiceClient):
    async def get(self, path: str, **kwargs) -> dict:
        headers = kwargs.pop("headers", {})
        inject(headers)   # adds traceparent, tracestate headers
        return await super().get(path, headers=headers, **kwargs)

# Inbound — extract trace context from headers (FastAPI middleware)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)  # auto-extracts incoming context
```

---

## Saga Pattern — Distributed Transactions

When an operation spans multiple services, use sagas to handle partial failures.

```python
# Choreography saga — services react to events, each rolls back on failure
# Example: Order placement spans api-service, billing-service, inventory-service

# Step 1: api-service creates order (PENDING)
async def place_order(order_data, user):
    order = await order_repo.create({**order_data, "status": "pending"})
    await bus.publish("orders.events", "order.created", {"order_id": order.public_id, ...})
    return order

# Step 2: billing-service reserves payment, publishes result
@consumer("orders.events", "order.created")
async def on_order_created(payload):
    try:
        await reserve_payment(payload["order_id"], payload["amount"])
        await bus.publish("billing.events", "payment.reserved", {"order_id": payload["order_id"]})
    except InsufficientFundsError:
        await bus.publish("billing.events", "payment.failed", {"order_id": payload["order_id"]})

# Step 3: api-service listens — confirms or cancels order
@consumer("billing.events", "payment.reserved")
async def on_payment_reserved(payload):
    await order_repo.update_status(payload["order_id"], "confirmed")

@consumer("billing.events", "payment.failed")
async def on_payment_failed(payload):
    await order_repo.update_status(payload["order_id"], "cancelled")
    # Compensate: notify user, restock inventory
    await bus.publish("orders.events", "order.cancelled", {"order_id": payload["order_id"]})
```

---

## Shared Nothing — Each Service Owns Its DB

```
api-service          → postgres: myapp_api
billing-service      → postgres: myapp_billing
notification-service → postgres: myapp_notifications

# Never share a DB between services
# Cross-service data access = call the API, not a JOIN
```

```python
# ❌ Never: direct DB query to another service's table
users = session.execute(select(User).where(User.tenant_id == tenant_id))

# ✅ Always: call the service's API
users = await api_client.get(f"/internal/tenants/{tenant_id}/users")
```

---

## Health Checks — Each Service

```python
# Every service exposes /health — API gateway checks before routing
@router.get("/health")
async def health():
    checks = {}
    checks["database"] = await check_db()
    checks["redis"]    = await check_redis()
    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ok" if all_ok else "degraded", **checks},
        status_code=200 if all_ok else 503,
    )
```

---

## Microservices Checklist

- [ ] Extract services only when monolith pain is real — not for fashion
- [ ] Each service owns its own database — no shared DB
- [ ] Sync HTTP for user-facing reads, async messaging for writes/events
- [ ] Service-to-service auth — JWT shared secret or mTLS
- [ ] Distributed tracing (OpenTelemetry) — `traceparent` propagated in all headers
- [ ] Saga pattern for cross-service transactions — compensating actions on failure
- [ ] Kubernetes DNS for service discovery — no extra service registry
- [ ] API gateway handles routing, rate limiting, TLS termination
- [ ] Each service has `/health` endpoint — gateway skips unhealthy services
- [ ] Circuit breaker on every external service call (see `resilience.md`)
- [ ] Consumer groups for async messaging — each service processes independently
- [ ] Dead letter queue — failed messages don't block the stream
