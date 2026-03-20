# Feature Flags

Feature flags enable gradual rollouts, A/B testing, and runtime configuration control — **without touching frontend code**.

## Key Concepts
- **Multi-tenant** - Per-tenant flag overrides
- **Gradual rollouts** - Deterministic percentage-based bucketing
- **User/group targeting** - Explicitly enable flags for users or groups
- **Environment gates** - Restrict flags to staging, production, etc.
- **Pluggable storage** - Django ORM, SQLAlchemy async, or in-memory YAML
- **Pluggable cache** - Request-scoped local or distributed Redis

**Libraries to consider:** [FlagForge](https://github.com/nayanjaiswal1/flagforge-feature-flags), [Unleash](https://github.com/Unleash/unleash), [GrowthBook](https://github.com/growthbook/growthbook)

## Resolution Priority
1. Environment gate
2. User targeting
3. Group targeting
4. Tenant override
5. Default + rollout percentage

---

## Flags vs Permissions — Key Distinction

| | Feature Flags | Permissions |
|--|---------------|-------------|
| Controls | **Feature availability** (is this built?) | **User authorization** (can this user do it?) |
| Example | `new-dashboard-ui: true` | `users: [read, delete]` |
| Where | `meta.flags` or separate endpoint | `meta.permissions` per response |
| Changes | Ops/config change | Role/policy change |

> Never use flags as a substitute for permissions, and vice versa.

---

## How It Fits With SDUI

Feature flags are **fetched once at app startup** and cached globally — not per-request like `meta.filters` or `meta.columns`.

```
App starts → fetch all flags once → cache globally → useFlag() anywhere
```

This is different from `meta.permissions` which is returned per API response.

---

## Backend — FastAPI Endpoint

```python
# api/v1/endpoints/flags.py
from fastapi import APIRouter, Depends
from app.core.feature_flags import get_flags_for_user
from app.dependencies.auth import get_current_user

router = APIRouter()

@router.get("/flags")
async def list_flags(current_user=Depends(get_current_user)):
    """Returns all flags resolved for the current user/tenant."""
    return await get_flags_for_user(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )
# Response:
# {
#   "new-dashboard-ui": true,
#   "bulk-export": false,
#   "ai-assistant": true
# }
```

---

## React Integration — Write Once, Never Touch

### 1. Fetch flags once at app startup

```tsx
// hooks/useFlags.ts
import { useQuery } from '@tanstack/react-query';

export function useFlags() {
  return useQuery<Record<string, boolean>>({
    queryKey: ['flags'],
    queryFn: () =>
      fetch('/api/v1/flags', { credentials: 'include' }).then(r => r.json()),
    staleTime: 1000 * 60 * 5,   // 5 minutes
    gcTime: 1000 * 60 * 30,
  });
}

export function useFlag(key: string): boolean {
  const { data } = useFlags();
  return data?.[key] ?? false;
}
```

### 2. FlagProvider — wraps app, fetches once

```tsx
// providers/FlagProvider.tsx
import { createContext, useContext } from 'react';
import { useQuery } from '@tanstack/react-query';

const FlagContext = createContext<Record<string, boolean>>({});

export function FlagProvider({ children }: { children: React.ReactNode }) {
  const { data: flags = {} } = useQuery<Record<string, boolean>>({
    queryKey: ['flags'],
    queryFn: () =>
      fetch('/api/v1/flags', { credentials: 'include' }).then(r => r.json()),
    staleTime: 1000 * 60 * 5,
  });

  return <FlagContext.Provider value={flags}>{children}</FlagContext.Provider>;
}

export function useFlag(key: string): boolean {
  return useContext(FlagContext)[key] ?? false;
}

// App.tsx — wrap once, never touch again
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <FlagProvider>
        <Router />
      </FlagProvider>
    </QueryClientProvider>
  );
}
```

### 3. Feature component — declarative conditional rendering

```tsx
// components/Feature.tsx — write once, never touch
interface FeatureProps {
  flag: string;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export function Feature({ flag, children, fallback = null }: FeatureProps) {
  const enabled = useFlag(flag);
  return <>{enabled ? children : fallback}</>;
}
```

### 4. Usage — never hardcode flag values

```tsx
// ❌ Never hardcode feature availability
{user.role === 'beta' && <NewDashboard />}

// ✅ Always driven by backend flag
<Feature flag="new-dashboard-ui">
  <NewDashboard />
</Feature>

// ✅ With fallback
<Feature flag="ai-assistant" fallback={<LegacySearch />}>
  <AISearch />
</Feature>

// ✅ Imperative usage
function ExportButton() {
  const bulkExportEnabled = useFlag('bulk-export');

  if (!bulkExportEnabled) return null;
  return <button onClick={handleExport}>Export</button>;
}
```

---

## CLI
- `flagforge sync` - Sync YAML config to database
- `flagforge enable/disable` - Toggle flags per tenant

---

## Flag Lifecycle
- Every flag should have an **expiry date**
- **Quarterly flag audit** — review and remove stale flags
- **Cleanup process**: disable → remove code → delete from database
- Track flag **owner and purpose** in flag metadata
- Flags left in code after launch become technical debt — hard to track and slow down decisions

### Checklist Before Removing a Flag
- [ ] Flag enabled for 100% of users
- [ ] No code paths remain for the disabled state
- [ ] Old code removed
- [ ] Flag deleted from database
