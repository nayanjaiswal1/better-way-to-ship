# Email Deliverability

## DNS Records — SPF, DKIM, DMARC

These three records prove you own the domain and authorize your sending service. Without them, email lands in spam.

### SPF — Authorize Sending Servers

```dns
# TXT record on example.com
# "Only these servers may send email for example.com"
example.com. TXT "v=spf1 include:sendgrid.net include:amazonses.com ~all"

# ~all = softfail (quarantine) — start here before moving to -all
# -all = hardfail (reject)    — use after confirming all senders are listed
```

### DKIM — Cryptographically Sign Emails

Each provider gives you a public key to add as a DNS TXT record.

```dns
# SendGrid
s1._domainkey.example.com. TXT "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA..."

# Amazon SES (auto-generated per region)
amazon._domainkey.example.com. CNAME "amazon._domainkey.us-east-1.amazonses.com"
```

### DMARC — Policy: What to Do with Failures

```dns
# Start with p=none (monitor only), then tighten
_dmarc.example.com. TXT "v=DMARC1; p=none; rua=mailto:dmarc@example.com; ruf=mailto:dmarc@example.com; fo=1"

# After reviewing reports (1-2 weeks), move to quarantine
_dmarc.example.com. TXT "v=DMARC1; p=quarantine; pct=25; rua=mailto:dmarc@example.com"

# Final: reject — failed messages dropped
_dmarc.example.com. TXT "v=DMARC1; p=reject; rua=mailto:dmarc@example.com; ruf=mailto:dmarc@example.com"
```

```
p=none       → monitor only, take no action
p=quarantine → send to spam folder
p=reject     → drop the email entirely

pct=25 → apply policy to 25% of messages (ramp up gradually)
rua    → aggregate reports (daily digest)
ruf    → forensic reports (per-failure detail)
```

### Verify Setup

```bash
# Check SPF
dig TXT example.com | grep spf

# Check DKIM (replace selector with your provider's value)
dig TXT s1._domainkey.example.com

# Check DMARC
dig TXT _dmarc.example.com

# Full email test — shows spam score + what's misconfigured
# Use: mail-tester.com or mxtoolbox.com
```

---

## Subdomain for Transactional Email

Send transactional email from a subdomain — protects your root domain's reputation.

```
From: noreply@mail.example.com   ✅ subdomain — isolated reputation
From: noreply@example.com        ⚠️ root domain — one spam incident tanks everything
```

```dns
# Add SPF, DKIM, DMARC for mail.example.com separately
mail.example.com. TXT "v=spf1 include:sendgrid.net -all"
_dmarc.mail.example.com. TXT "v=DMARC1; p=reject; rua=mailto:dmarc@example.com"
```

---

## Sending — Django

```python
# config/settings/base.py
EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"

ANYMAIL = {
    "SENDGRID_API_KEY": env("SENDGRID_API_KEY"),
}

DEFAULT_FROM_EMAIL = "MyApp <noreply@mail.example.com>"
SERVER_EMAIL       = "errors@mail.example.com"
```

```bash
pip install django-anymail[sendgrid]
# or
pip install django-anymail[mailgun]
pip install django-anymail[ses]
```

```python
# common/email.py — base email class
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

def send_transactional_email(
    to: str,
    subject: str,
    template: str,
    context: dict,
    unsubscribe_url: str | None = None,
) -> None:
    """
    Render template + send with correct headers.
    Always call via Celery task — never block a request.
    """
    html = render_to_string(f"emails/{template}.html", context)
    text = render_to_string(f"emails/{template}.txt",  context)

    headers = {}
    if unsubscribe_url:
        headers["List-Unsubscribe"]      = f"<{unsubscribe_url}>"
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"  # RFC 8058 one-click

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=None,    # uses DEFAULT_FROM_EMAIL
        to=[to],
        headers=headers,
    )
    msg.attach_alternative(html, "text/html")
    msg.send()
```

---

## Sending — FastAPI

```python
# core/email.py
import httpx
from app.config import settings

async def send_email(
    to: str,
    subject: str,
    html: str,
    text: str,
    unsubscribe_url: str | None = None,
) -> None:
    headers = {"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"}
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": "noreply@mail.example.com", "name": "MyApp"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html",  "value": html},
        ],
    }
    if unsubscribe_url:
        payload["headers"] = {
            "List-Unsubscribe":      f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
```

---

## Bounce & Complaint Handling

Bounces and spam complaints destroy your sender reputation. Handle them.

### SendGrid Webhook

```python
# apps/email/views.py — handle SendGrid event webhook
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

class SendGridWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Verify webhook signature (SendGrid signs events)
        # https://docs.sendgrid.com/for-developers/tracking-events/getting-started-event-webhook-security-features
        events = request.data  # list of events

        for event in events:
            event_type = event.get("event")

            if event_type == "bounce":
                handle_bounce.delay(
                    email=event["email"],
                    bounce_type=event.get("type", "bounce"),
                    reason=event.get("reason", ""),
                )

            elif event_type == "spamreport":
                handle_spam_complaint.delay(email=event["email"])

            elif event_type == "unsubscribe":
                handle_unsubscribe.delay(email=event["email"])

        return Response({"ok": True})
```

```python
# apps/email/tasks.py
from celery import shared_task

@shared_task
def handle_bounce(email: str, bounce_type: str, reason: str) -> None:
    from apps.users.models import User, EmailBounce

    # Log bounce
    EmailBounce.objects.get_or_create(
        email=email,
        defaults={"bounce_type": bounce_type, "reason": reason},
    )

    if bounce_type == "bounce":
        # Hard bounce — permanently undeliverable, stop sending immediately
        User.objects.filter(email=email).update(email_bounced=True)

@shared_task
def handle_spam_complaint(email: str) -> None:
    """User marked email as spam — unsubscribe them from all marketing."""
    from apps.notifications.models import NotificationPreference
    NotificationPreference.objects.filter(
        user__email=email
    ).update(
        marketing_email=False,
        weekly_digest_email=False,
    )

@shared_task
def handle_unsubscribe(email: str) -> None:
    from apps.notifications.models import NotificationPreference
    NotificationPreference.objects.filter(
        user__email=email
    ).update(marketing_email=False)
```

```python
# Block sending to bounced addresses
def send_transactional_email(to: str, ...):
    from apps.users.models import User
    if User.objects.filter(email=to, email_bounced=True).exists():
        return  # silently skip — don't retry bounced addresses
    ...
```

---

## Unsubscribe

Every marketing email must have an unsubscribe link. Transactional emails (receipts, password reset) are exempt.

```python
# apps/users/models.py
import secrets

class User(AbstractBaseUser, ...):
    unsubscribe_token = models.CharField(
        max_length=64,
        default=secrets.token_urlsafe,
        unique=True,
    )
    email_unsubscribed = models.BooleanField(default=False)
    email_bounced      = models.BooleanField(default=False)
```

```python
# apps/email/views.py — one-click unsubscribe (RFC 8058)
class UnsubscribeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        """One-click unsubscribe — email clients call this automatically."""
        token = request.data.get("token") or request.query_params.get("token")
        if not token:
            return Response(status=400)
        User.objects.filter(unsubscribe_token=token).update(email_unsubscribed=True)
        return Response({"ok": True})

    def get(self, request):
        """Human-visible unsubscribe page."""
        token = request.query_params.get("token")
        # Show a page confirming unsubscription
        return render(request, "email/unsubscribed.html")
```

```python
# Generate unsubscribe URL for every marketing email
def get_unsubscribe_url(user) -> str:
    return f"https://app.example.com/unsubscribe?token={user.unsubscribe_token}"
```

---

## Email Templates

```html
<!-- templates/emails/base.html — responsive, tested in major clients -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block subject %}{% endblock %}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
             background: #f9fafb; margin: 0; padding: 24px;">
  <div style="max-width: 600px; margin: 0 auto; background: #fff;
              border-radius: 8px; padding: 32px;">

    <img src="https://app.example.com/logo.png" alt="MyApp" height="32"
         style="margin-bottom: 24px;">

    {% block content %}{% endblock %}

    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">

    <p style="font-size: 12px; color: #9ca3af; margin: 0;">
      MyApp Inc, 123 Main St, San Francisco CA 94105
      <br>
      <a href="{{ unsubscribe_url }}" style="color: #9ca3af;">Unsubscribe</a>
    </p>
  </div>
</body>
</html>
```

```html
<!-- templates/emails/order_confirmation.html -->
{% extends "emails/base.html" %}

{% block content %}
<h1 style="font-size: 24px; color: #111827; margin: 0 0 16px;">
  Order confirmed
</h1>
<p style="color: #374151;">
  Hi {{ order.created_by.name }},<br>
  Your order <strong>{{ order.reference }}</strong> has been confirmed.
</p>
<table style="width: 100%; border-collapse: collapse; margin: 24px 0;">
  <tr>
    <td style="padding: 8px 0; color: #374151;">Total</td>
    <td style="padding: 8px 0; text-align: right; font-weight: 600;">${{ order.amount }}</td>
  </tr>
</table>
<a href="https://app.example.com/orders/{{ order.public_id }}"
   style="display: inline-block; background: #3b82f6; color: #fff;
          padding: 12px 24px; border-radius: 6px; text-decoration: none;">
  View Order
</a>
{% endblock %}
```

---

## Testing Deliverability

```bash
# Local dev — catch all emails without sending
docker run -p 1025:1025 -p 8025:8025 axllent/mailpit

# config/settings/development.py
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST     = "localhost"
EMAIL_PORT     = 1025   # Mailpit SMTP
# View emails at http://localhost:8025
```

```bash
# Check spam score before launching
# Use mail-tester.com — send a test email, get a score
# Target: 10/10

# Common issues:
# - Missing List-Unsubscribe header     → add it
# - No plain-text version               → always send text + HTML
# - Image-only emails                   → add text content
# - Links redirect through tracking URL → use direct links or trusted tracking
# - High image-to-text ratio            → add more text content
```

---

## Email Deliverability Checklist

### DNS
- [ ] SPF record — authorizes your sending service
- [ ] DKIM — signatures verified by receiving servers
- [ ] DMARC — policy set, reports flowing to `rua` address
- [ ] Sending from subdomain (`mail.example.com`) — not root domain

### Code
- [ ] Every marketing email has `List-Unsubscribe` header (RFC 8058)
- [ ] One-click unsubscribe endpoint (`POST /unsubscribe`)
- [ ] Every email has a plain-text alternative
- [ ] Hard bounces update `email_bounced=True` — never retry
- [ ] Spam complaints trigger unsubscription
- [ ] `unsubscribe_token` unique per user — rotate on use

### Sending
- [ ] Never send marketing to `email_unsubscribed=True` users
- [ ] Never send to `email_bounced=True` addresses
- [ ] All email sending via Celery — never block a request
- [ ] SendGrid / SES event webhook set up and handling bounces
- [ ] Local dev uses Mailpit — no real emails sent
- [ ] mail-tester.com score: 10/10 before launch
