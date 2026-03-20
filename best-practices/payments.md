# Payments — Stripe

## Architecture

```
User → Frontend → Backend → Stripe
                         ← webhook (async)
                ← success
```

- **Never handle card data** — Stripe Elements handles it entirely
- **Verify everything server-side** — never trust frontend for amounts/plans
- **Webhooks are the source of truth** — not redirect callbacks

```bash
pip install stripe
npm install @stripe/stripe-js @stripe/react-stripe-js
```

---

## Backend

### Config

```python
# core/config.py
class Settings(BaseSettings):
    STRIPE_SECRET_KEY: str              # sk_live_... or sk_test_...
    STRIPE_WEBHOOK_SECRET: str          # whsec_...
    STRIPE_PRICE_ID_PRO: str           # price_...
    STRIPE_PRICE_ID_ENTERPRISE: str    # price_...
```

### Customer & Subscription Service

```python
# services/billing_service.py
import stripe
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

class BillingService:
    async def get_or_create_customer(self, user: User) -> str:
        """Each user maps to one Stripe customer."""
        if user.stripe_customer_id:
            return user.stripe_customer_id

        customer = stripe.Customer.create(
            email=user.email,
            name=user.name,
            metadata={"user_id": user.public_id, "tenant_id": str(user.tenant_id)},
        )
        await self.user_repo.update(user.id, {"stripe_customer_id": customer.id})
        return customer.id

    async def create_checkout_session(self, user: User, price_id: str) -> str:
        """Returns checkout URL — redirect user there."""
        customer_id = await self.get_or_create_customer(user)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{settings.FRONTEND_URL}/billing/success?session={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.FRONTEND_URL}/billing/cancelled",
            allow_promotion_codes=True,
            metadata={"tenant_id": str(user.tenant_id)},
        )
        return session.url

    async def create_portal_session(self, user: User) -> str:
        """Returns billing portal URL — manage subscription, invoices, cancel."""
        customer_id = await self.get_or_create_customer(user)

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{settings.FRONTEND_URL}/settings/billing",
        )
        return session.url
```

### Endpoints

```python
# api/v1/endpoints/billing.py
from fastapi import APIRouter, Request, HTTPException
import stripe

router = APIRouter()

@router.post("/billing/checkout")
async def create_checkout(
    price_id: str,
    current_user=Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
):
    # Validate price_id is one we actually offer — never trust client
    allowed = {settings.STRIPE_PRICE_ID_PRO, settings.STRIPE_PRICE_ID_ENTERPRISE}
    if price_id not in allowed:
        raise AppValidationError("Invalid plan")

    url = await service.create_checkout_session(current_user, price_id)
    return {"checkout_url": url}

@router.post("/billing/portal")
async def billing_portal(
    current_user=Depends(get_current_user),
    service: BillingService = Depends(get_billing_service),
):
    url = await service.create_portal_session(current_user)
    return {"portal_url": url}

@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, service: BillingService = Depends(get_billing_service)):
    """Stripe sends events here — verify signature, update DB."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    await service.handle_webhook(event)
    return {"received": True}
```

### Webhook Handler — source of truth

```python
# services/billing_service.py
class BillingService:
    async def handle_webhook(self, event: stripe.Event):
        """
        Webhooks can arrive out of order or multiple times.
        Always idempotent — safe to process same event twice.
        """
        match event.type:
            case "checkout.session.completed":
                await self._handle_checkout_completed(event.data.object)

            case "customer.subscription.updated":
                await self._handle_subscription_updated(event.data.object)

            case "customer.subscription.deleted":
                await self._handle_subscription_cancelled(event.data.object)

            case "invoice.payment_failed":
                await self._handle_payment_failed(event.data.object)

            case _:
                pass  # ignore unhandled events

    async def _handle_checkout_completed(self, session):
        tenant_id = int(session.metadata["tenant_id"])
        subscription_id = session.subscription

        subscription = stripe.Subscription.retrieve(subscription_id)
        plan = self._plan_from_price(subscription.items.data[0].price.id)

        await self.tenant_repo.update(tenant_id, {
            "stripe_subscription_id": subscription_id,
            "plan": plan,
            "plan_status": "active",
            "current_period_end": datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc),
        })

    async def _handle_subscription_cancelled(self, subscription):
        await self.tenant_repo.update_by_stripe_id(subscription.customer, {
            "plan": "free",
            "plan_status": "cancelled",
        })

    async def _handle_payment_failed(self, invoice):
        # Notify user — don't immediately downgrade
        tenant = await self.tenant_repo.get_by_stripe_customer(invoice.customer)
        await self.notification_service.create(
            user_id=tenant.owner_id,
            type="warning",
            title="Payment failed",
            body="Update your payment method to keep your subscription active.",
            action_url="/settings/billing",
        )

    def _plan_from_price(self, price_id: str) -> str:
        return {
            settings.STRIPE_PRICE_ID_PRO: "pro",
            settings.STRIPE_PRICE_ID_ENTERPRISE: "enterprise",
        }.get(price_id, "free")
```

### Model changes

```python
# models/tenant.py
class Tenant(Base):
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    plan: Mapped[str] = mapped_column(String(20), default="free")
    plan_status: Mapped[str] = mapped_column(String(20), default="active")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

---

## React — Stripe Elements

```tsx
// providers/StripeProvider.tsx
import { loadStripe } from '@stripe/stripe-js';
import { Elements } from '@stripe/react-stripe-js';

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY);

export function StripeProvider({ children }: { children: React.ReactNode }) {
  return <Elements stripe={stripePromise}>{children}</Elements>;
}

// components/UpgradeButton.tsx
function UpgradeButton({ plan }: { plan: 'pro' | 'enterprise' }) {
  const checkout = useMutation({
    mutationFn: (priceId: string) =>
      fetch('/api/v1/billing/checkout', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ price_id: priceId }),
      }).then(r => r.json()),
    onSuccess: ({ checkout_url }) => {
      window.location.href = checkout_url;  // redirect to Stripe hosted checkout
    },
  });

  const priceIds = {
    pro: import.meta.env.VITE_STRIPE_PRICE_PRO,
    enterprise: import.meta.env.VITE_STRIPE_PRICE_ENTERPRISE,
  };

  return (
    <button onClick={() => checkout.mutate(priceIds[plan])}>
      Upgrade to {plan}
    </button>
  );
}

// components/ManageBillingButton.tsx
function ManageBillingButton() {
  const portal = useMutation({
    mutationFn: () =>
      fetch('/api/v1/billing/portal', { method: 'POST', credentials: 'include' })
        .then(r => r.json()),
    onSuccess: ({ portal_url }) => {
      window.location.href = portal_url;
    },
  });

  return <button onClick={() => portal.mutate()}>Manage billing</button>;
}
```

---

## Plan-Based Feature Gating

```python
# core/plan_limits.py
PLAN_LIMITS = {
    "free":       {"users": 5,   "storage_gb": 1,   "api_calls_per_month": 1000},
    "pro":        {"users": 50,  "storage_gb": 50,  "api_calls_per_month": 50000},
    "enterprise": {"users": -1,  "storage_gb": -1,  "api_calls_per_month": -1},  # -1 = unlimited
}

async def check_plan_limit(tenant: Tenant, resource: str, current_count: int):
    limit = PLAN_LIMITS.get(tenant.plan, {}).get(resource, 0)
    if limit != -1 and current_count >= limit:
        raise ForbiddenError(f"Plan limit reached for {resource}. Upgrade to continue.")
```

```tsx
// React — show upgrade prompt from meta
function UsersPage() {
  const { schema } = useResource('users');
  const tenant = useTenant();

  return (
    <>
      {schema?.plan_limit_reached && (
        <Banner variant="warning">
          You've reached your plan limit. <UpgradeButton plan="pro" />
        </Banner>
      )}
      <DataTable ... />
    </>
  );
}
```
