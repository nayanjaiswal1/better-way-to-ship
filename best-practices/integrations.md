# Integrations

## Outbound Webhooks

Let external systems subscribe to events in your app — no polling needed on their side.

```
Your app → event happens → POST to subscriber URL → retry on failure
```

### Models

```python
# models/webhook.py
from sqlalchemy import String, BigInteger, Boolean, JSON, Index
from ulid import ULID

class WebhookSubscription(Base, SoftDeleteMixin):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(26), default=lambda: str(ULID()), unique=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger)
    url: Mapped[str] = mapped_column(String)
    secret: Mapped[str] = mapped_column(String)      # used to sign payloads
    events: Mapped[list[str]] = mapped_column(JSON)  # ["user.created", "order.completed"]
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_webhook_subscriptions_tenant", "tenant_id", "active"),
    )

class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))  # pending, delivered, failed
    attempts: Mapped[int] = mapped_column(default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_status: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

### Webhook Service — sign and deliver

```python
# services/webhook_service.py
import hmac, hashlib, json
import httpx
from datetime import datetime, timezone, timedelta

class WebhookService:
    def __init__(self, repo: WebhookRepository, event_bus: EventBus):
        self.repo = repo
        self.event_bus = event_bus

    def sign_payload(self, secret: str, payload: dict, timestamp: int) -> str:
        """HMAC-SHA256 signature — subscriber verifies this to trust the payload."""
        message = f"{timestamp}.{json.dumps(payload, sort_keys=True)}"
        return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    async def dispatch(self, tenant_id: int, event_type: str, payload: dict):
        """Called after domain events — fan out to all matching subscriptions."""
        subscriptions = await self.repo.get_active_for_event(tenant_id, event_type)

        for sub in subscriptions:
            delivery = await self.repo.create_delivery(WebhookDelivery(
                subscription_id=sub.id,
                event_type=event_type,
                payload=payload,
                status="pending",
            ))
            # Deliver via ARQ worker — not inline
            await self.event_bus.publish(DomainEvent(
                event_type="webhook.dispatch",
                payload={"delivery_id": delivery.id},
                tenant_id=tenant_id,
            ))

    async def deliver(self, delivery_id: int):
        """Called by ARQ worker."""
        delivery = await self.repo.get_delivery(delivery_id)
        sub = await self.repo.get_subscription(delivery.subscription_id)

        timestamp = int(datetime.now(timezone.utc).timestamp())
        signature = self.sign_payload(sub.secret, delivery.payload, timestamp)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    sub.url,
                    json=delivery.payload,
                    headers={
                        "X-Webhook-Event": delivery.event_type,
                        "X-Webhook-Signature": signature,
                        "X-Webhook-Timestamp": str(timestamp),
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code < 300:
                await self.repo.mark_delivered(delivery.id, resp.status_code)
            else:
                await self._schedule_retry(delivery, resp.status_code)

        except Exception:
            await self._schedule_retry(delivery, None)

    async def _schedule_retry(self, delivery: WebhookDelivery, status: int | None):
        """Exponential backoff: 1m, 5m, 30m, 2h, 24h."""
        delays = [1, 5, 30, 120, 1440]  # minutes
        attempt = delivery.attempts + 1

        if attempt > len(delays):
            await self.repo.mark_failed(delivery.id, status)
            return

        next_retry = datetime.now(timezone.utc) + timedelta(minutes=delays[attempt - 1])
        await self.repo.schedule_retry(delivery.id, attempt, next_retry, status)
```

### API — manage subscriptions

```python
# api/v1/endpoints/webhooks.py
import secrets

@router.post("/webhooks", response_model=WebhookSubscriptionResponse)
async def create_webhook(
    data: WebhookCreate,
    current_user=Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
):
    secret = secrets.token_hex(32)  # subscriber saves this to verify signatures
    return await service.create_subscription(
        tenant_id=current_user.tenant_id,
        url=data.url,
        events=data.events,
        secret=secret,
    )

@router.post("/webhooks/{public_id}/test")
async def test_webhook(public_id: str, service=Depends(get_webhook_service)):
    """Send a test payload so subscriber can verify their endpoint."""
    await service.dispatch(
        tenant_id=...,
        event_type="webhook.test",
        payload={"message": "This is a test webhook delivery"},
    )
```

### Subscriber — verify signature (example in Python)

```python
# How your customers verify your webhooks
import hmac, hashlib, json

def verify_webhook(secret: str, payload: bytes, signature: str, timestamp: str) -> bool:
    message = f"{timestamp}.{payload.decode()}"
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

---

## Sentry — Error Tracking

Catch and track errors in production — both backend and frontend.

### Backend

```bash
pip install sentry-sdk[fastapi]
```

```python
# main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.arq import ArqIntegration

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    environment=settings.ENVIRONMENT,         # production, staging
    release=settings.APP_VERSION,
    integrations=[
        FastApiIntegration(transaction_style="endpoint"),
        SqlalchemyIntegration(),
        ArqIntegration(),
    ],
    traces_sample_rate=0.1,    # 10% of requests traced — adjust per traffic volume
    profiles_sample_rate=0.1,
    send_default_pii=False,    # never send PII to Sentry
)

# Attach user context to every error
@app.middleware("http")
async def attach_sentry_user(request: Request, call_next):
    token_data = getattr(request.state, "token_data", None)
    if token_data:
        sentry_sdk.set_user({"id": token_data.get("sub")})  # no email — PII
    return await call_next(request)
```

### React

```bash
npm install @sentry/react
```

```tsx
// main.tsx
import * as Sentry from '@sentry/react';

Sentry.init({
  dsn: import.meta.env.VITE_SENTRY_DSN,
  environment: import.meta.env.VITE_ENV,
  release: import.meta.env.VITE_APP_VERSION,
  integrations: [
    Sentry.browserTracingIntegration(),
    Sentry.replayIntegration({
      maskAllText: true,    // mask PII in session replays
      blockAllMedia: true,
    }),
  ],
  tracesSampleRate: 0.1,
  replaysOnErrorSampleRate: 1.0,  // always capture replay on error
  replaysSessionSampleRate: 0.05, // 5% of sessions
});

// Wrap app with Sentry error boundary
createRoot(document.getElementById('root')!).render(
  <Sentry.ErrorBoundary fallback={<ErrorPage />}>
    <App />
  </Sentry.ErrorBoundary>
);

// Attach user context after login
export function attachSentryUser(userId: string) {
  Sentry.setUser({ id: userId });  // id only — no email (PII)
}

// Clear on logout
export function clearSentryUser() {
  Sentry.setUser(null);
}
```

### Custom error capture

```python
# backend — capture with context
import sentry_sdk

try:
    await payment_gateway.charge(amount, token)
except Exception as e:
    sentry_sdk.capture_exception(e, extras={
        "amount": amount,
        "tenant_id": tenant_id,
        # never log card tokens or PII
    })
    raise
```

```tsx
// frontend — capture manually
import * as Sentry from '@sentry/react';

try {
  await submitOrder(data);
} catch (error) {
  Sentry.captureException(error, {
    extra: { orderId: data.id },
  });
}
```
