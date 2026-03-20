# GDPR Compliance

## Core Rights to Implement

| Right | What it means | Implementation |
|-------|--------------|----------------|
| Right to access | User can download all their data | `/api/v1/me/export` endpoint |
| Right to erasure | User can delete their account + data | `/api/v1/me/delete` endpoint |
| Right to rectification | User can correct their data | Standard update endpoints |
| Data portability | Export in machine-readable format | JSON/CSV export |
| Consent | Must get explicit consent for non-essential processing | Cookie consent banner |

---

## Data Export (Right to Access)

```python
# services/gdpr_service.py
import json
from datetime import datetime, timezone

class GDPRService:
    async def export_user_data(self, user_id: int) -> dict:
        """Collect all data associated with the user — machine readable."""
        user = await self.user_repo.get_by_id(user_id)
        posts = await self.post_repo.get_by_user(user_id)
        orders = await self.order_repo.get_by_user(user_id)
        notifications = await self.notification_repo.get_by_user(user_id)
        audit_logs = await self.audit_repo.get_by_user(user_id)

        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user": {
                "id": user.public_id,
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at.isoformat(),
            },
            "posts": [
                {"id": p.public_id, "title": p.title, "created_at": p.created_at.isoformat()}
                for p in posts
            ],
            "orders": [
                {"id": o.public_id, "total": o.total, "created_at": o.created_at.isoformat()}
                for o in orders
            ],
            "audit_log": [
                {"action": a.action, "at": a.created_at.isoformat()}
                for a in audit_logs
            ],
        }

# api/v1/endpoints/gdpr.py
@router.get("/me/export")
async def export_my_data(
    current_user=Depends(get_current_user),
    service: GDPRService = Depends(get_gdpr_service),
):
    """GDPR data export — returns all data for the current user."""
    data = await service.export_user_data(current_user.id)

    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=my-data.json"},
    )
```

---

## Right to Erasure

```python
# services/gdpr_service.py
class GDPRService:
    async def erase_user(self, user_id: int, reason: str = "user_request"):
        """
        GDPR erasure — anonymize PII, keep non-personal records for compliance.
        Hard delete is rarely the right approach — orders, audit logs must be kept.
        """
        async with self.session.begin():
            # 1. Anonymize PII — don't hard delete (breaks audit trail, foreign keys)
            await self.session.execute(
                update(User)
                .where(User.id == user_id)
                .values(
                    email=f"deleted_{user_id}@removed.invalid",
                    name="Deleted User",
                    hashed_password=None,
                    mfa_secret=None,
                    deleted_at=datetime.now(timezone.utc),
                )
            )

            # 2. Delete genuinely personal content
            await self.session.execute(
                delete(Post).where(Post.user_id == user_id)
            )
            await self.session.execute(
                delete(Notification).where(Notification.user_id == user_id)
            )

            # 3. Revoke all tokens
            await self.session.execute(
                delete(RefreshToken).where(RefreshToken.user_id == user_id)
            )

            # 4. Audit the erasure itself — keep for compliance
            await self.audit_repo.log(
                user_id=user_id,
                action="gdpr_erasure",
                metadata={"reason": reason},
            )

# api/v1/endpoints/gdpr.py
@router.delete("/me")
async def delete_my_account(
    password: str,                              # require password confirmation
    current_user=Depends(get_current_user),
    service: GDPRService = Depends(get_gdpr_service),
    user_service: UserService = Depends(get_user_service),
):
    # Verify identity before erasure
    await user_service.authenticate_user(current_user.email, password)
    await service.erase_user(current_user.id)
    return {"message": "Account deleted. Your data has been removed."}
```

---

## Cookie Consent

### React — consent banner

```tsx
// hooks/useCookieConsent.ts
type ConsentState = {
  analytics: boolean;
  marketing: boolean;
  functional: boolean;
};

const CONSENT_KEY = 'cookie_consent';

export function useCookieConsent() {
  const [consent, setConsent] = useState<ConsentState | null>(() => {
    const stored = localStorage.getItem(CONSENT_KEY);
    return stored ? JSON.parse(stored) : null;
  });

  const accept = (preferences: ConsentState) => {
    localStorage.setItem(CONSENT_KEY, JSON.stringify(preferences));
    setConsent(preferences);
    applyConsent(preferences);
  };

  const acceptAll = () => accept({ analytics: true, marketing: true, functional: true });
  const rejectAll = () => accept({ analytics: false, marketing: false, functional: false });

  return { consent, accept, acceptAll, rejectAll, hasConsented: consent !== null };
}

function applyConsent(consent: ConsentState) {
  // Enable/disable analytics based on consent
  if (consent.analytics) {
    window.posthog?.opt_in_capturing();
  } else {
    window.posthog?.opt_out_capturing();
  }
}

// components/CookieBanner.tsx
export function CookieBanner() {
  const { hasConsented, acceptAll, rejectAll, accept } = useCookieConsent();
  const [showDetails, setShowDetails] = useState(false);
  const [prefs, setPrefs] = useState({ analytics: false, marketing: false, functional: true });

  if (hasConsented) return null;

  return (
    <div className="cookie-banner" role="dialog" aria-label="Cookie consent">
      <p>
        We use cookies to improve your experience.
        <button onClick={() => setShowDetails(s => !s)}>Manage preferences</button>
      </p>

      {showDetails && (
        <div>
          <label>
            <input type="checkbox" checked={prefs.functional} disabled />
            Functional (required)
          </label>
          <label>
            <input
              type="checkbox"
              checked={prefs.analytics}
              onChange={e => setPrefs(p => ({ ...p, analytics: e.target.checked }))}
            />
            Analytics
          </label>
          <label>
            <input
              type="checkbox"
              checked={prefs.marketing}
              onChange={e => setPrefs(p => ({ ...p, marketing: e.target.checked }))}
            />
            Marketing
          </label>
          <button onClick={() => accept(prefs)}>Save preferences</button>
        </div>
      )}

      <div>
        <button onClick={rejectAll}>Reject all</button>
        <button onClick={acceptAll}>Accept all</button>
      </div>
    </div>
  );
}

// App.tsx — place at root
function App() {
  return (
    <>
      <Router />
      <CookieBanner />
    </>
  );
}
```

---

## Data Retention Policy

```python
# workers/cron.py — enforce retention automatically
async def enforce_data_retention(ctx):
    """
    Delete data older than retention period.
    Run monthly — not daily (gives time to catch mistakes).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * 2)  # 2 years

    # Soft-deleted users older than 2 years → full erasure
    old_deleted = await ctx["db"].execute(
        select(User.id).where(
            User.deleted_at.isnot(None),
            User.deleted_at < cutoff,
        )
    )
    for user_id in old_deleted.scalars():
        await ctx["gdpr_service"].erase_user(user_id, reason="retention_policy")

    # Audit logs older than 7 years → delete (legal minimum in most jurisdictions)
    await ctx["db"].execute(
        delete(AuditLog).where(
            AuditLog.created_at < datetime.now(timezone.utc) - timedelta(days=365 * 7)
        )
    )
```

---

## GDPR Checklist

- [ ] Privacy policy published and linked from app
- [ ] Cookie consent banner — no tracking before consent
- [ ] `GET /me/export` — data export in JSON
- [ ] `DELETE /me` — account erasure with password confirmation
- [ ] PII anonymized, not hard deleted (preserves audit trail)
- [ ] Data retention policy enforced automatically
- [ ] Audit log of all erasures
- [ ] Never log PII (emails, names, IPs) in application logs
- [ ] Data processing agreements with all third-party vendors
