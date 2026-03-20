# Frontend Patterns

## Dark Mode / Theming

### CSS Variables — single source of truth

```css
/* styles/tokens.css */
:root {
  /* Colors */
  --color-bg-primary:   #ffffff;
  --color-bg-secondary: #f9fafb;
  --color-text-primary: #111827;
  --color-text-muted:   #6b7280;
  --color-border:       #e5e7eb;
  --color-accent:       #3b82f6;
  --color-danger:       #ef4444;
  --color-success:      #22c55e;

  /* Spacing */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 48px;

  /* Typography */
  --font-size-sm:   0.875rem;
  --font-size-base: 1rem;
  --font-size-lg:   1.125rem;
  --font-size-xl:   1.25rem;
  --radius-sm: 4px;
  --radius-md: 8px;
}

/* Dark mode — override tokens only */
[data-theme="dark"] {
  --color-bg-primary:   #111827;
  --color-bg-secondary: #1f2937;
  --color-text-primary: #f9fafb;
  --color-text-muted:   #9ca3af;
  --color-border:       #374151;
}
```

```tsx
// hooks/useTheme.ts
type Theme = 'light' | 'dark' | 'system';

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() =>
    (localStorage.getItem('theme') as Theme) ?? 'system'
  );

  useEffect(() => {
    const root = document.documentElement;
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    if (theme === 'dark' || (theme === 'system' && prefersDark)) {
      root.setAttribute('data-theme', 'dark');
    } else {
      root.setAttribute('data-theme', 'light');
    }

    localStorage.setItem('theme', theme);
  }, [theme]);

  // Listen for system preference changes
  useEffect(() => {
    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => setTheme('system');  // re-trigger effect
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [theme]);

  return { theme, setTheme };
}

// ThemeToggle.tsx — write once, never touch
function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <select value={theme} onChange={e => setTheme(e.target.value as Theme)}>
      <option value="light">Light</option>
      <option value="dark">Dark</option>
      <option value="system">System</option>
    </select>
  );
}
```

### Tenant-specific theming

```tsx
// From bootstrap — tenant sends their brand colors
function applyTenantTheme(tenant: Tenant) {
  if (!tenant.brand_color) return;
  document.documentElement.style.setProperty('--color-accent', tenant.brand_color);
  document.documentElement.style.setProperty('--color-accent-dark', darken(tenant.brand_color, 10));
}

// TenantProvider applies on mount
export function TenantProvider({ children }) {
  const { data } = useQuery({ queryKey: ['bootstrap'] });

  useEffect(() => {
    if (data?.tenant) applyTenantTheme(data.tenant);
  }, [data?.tenant]);

  return <TenantContext.Provider value={data?.tenant}>{children}</TenantContext.Provider>;
}
```

---

## Headless Component Pattern

Separate logic from presentation — same behaviour, any UI.

```tsx
// hooks/useSelect.ts — logic only, no JSX
interface UseSelectOptions<T> {
  options: T[];
  value: T | null;
  onChange: (value: T) => void;
  getKey: (option: T) => string;
}

export function useSelect<T>({ options, value, onChange, getKey }: UseSelectOptions<T>) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [highlighted, setHighlighted] = useState(0);

  const filtered = options.filter(o =>
    getKey(o).toLowerCase().includes(search.toLowerCase())
  );

  const select = (option: T) => {
    onChange(option);
    setOpen(false);
    setSearch('');
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown': setHighlighted(h => Math.min(h + 1, filtered.length - 1)); break;
      case 'ArrowUp':   setHighlighted(h => Math.max(h - 1, 0)); break;
      case 'Enter':     if (filtered[highlighted]) select(filtered[highlighted]); break;
      case 'Escape':    setOpen(false); break;
    }
  };

  return { open, setOpen, search, setSearch, filtered, highlighted, select, onKeyDown };
}

// Styled Select — consumes hook, owns UI
function Select<T extends { id: string; label: string }>({
  options, value, onChange,
}: { options: T[]; value: T | null; onChange: (v: T) => void }) {
  const { open, setOpen, search, setSearch, filtered, highlighted, select, onKeyDown } =
    useSelect({ options, value, onChange, getKey: o => o.label });

  return (
    <div onKeyDown={onKeyDown}>
      <button onClick={() => setOpen(o => !o)}>
        {value?.label ?? 'Select...'}
      </button>
      {open && (
        <div>
          <input value={search} onChange={e => setSearch(e.target.value)} autoFocus />
          {filtered.map((opt, i) => (
            <div
              key={opt.id}
              className={i === highlighted ? 'highlighted' : ''}
              onClick={() => select(opt)}
            >
              {opt.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// You can use the same useSelect hook with a completely different UI
// (e.g. a mobile bottom sheet, a popover, a radio group)
```

### Compound Components

```tsx
// Compound component — flexible layout, shared state
const TabsContext = createContext<{ active: string; setActive: (v: string) => void } | null>(null);

function Tabs({ defaultTab, children }: { defaultTab: string; children: React.ReactNode }) {
  const [active, setActive] = useState(defaultTab);
  return (
    <TabsContext.Provider value={{ active, setActive }}>
      <div>{children}</div>
    </TabsContext.Provider>
  );
}

function TabList({ children }: { children: React.ReactNode }) {
  return <div role="tablist">{children}</div>;
}

function Tab({ value, children }: { value: string; children: React.ReactNode }) {
  const { active, setActive } = useContext(TabsContext)!;
  return (
    <button
      role="tab"
      aria-selected={active === value}
      onClick={() => setActive(value)}
    >
      {children}
    </button>
  );
}

function TabPanel({ value, children }: { value: string; children: React.ReactNode }) {
  const { active } = useContext(TabsContext)!;
  if (active !== value) return null;
  return <div role="tabpanel">{children}</div>;
}

// Attach as namespace
Tabs.List  = TabList;
Tabs.Tab   = Tab;
Tabs.Panel = TabPanel;

// Usage — fully composable
<Tabs defaultTab="users">
  <Tabs.List>
    <Tabs.Tab value="users">Users</Tabs.Tab>
    <Tabs.Tab value="roles">Roles</Tabs.Tab>
  </Tabs.List>
  <Tabs.Panel value="users"><UsersTable /></Tabs.Panel>
  <Tabs.Panel value="roles"><RolesTable /></Tabs.Panel>
</Tabs>
```

---

## Analytics — PostHog

Track user behaviour — understand what's actually used.

```bash
npm install posthog-js
```

```tsx
// lib/analytics.ts — wrap PostHog, write once
import posthog from 'posthog-js';

export function initAnalytics(userId?: string) {
  if (!import.meta.env.VITE_POSTHOG_KEY) return;

  posthog.init(import.meta.env.VITE_POSTHOG_KEY, {
    api_host: import.meta.env.VITE_POSTHOG_HOST ?? 'https://app.posthog.com',
    capture_pageview: true,
    capture_pageleave: true,
    persistence: 'localStorage',
    opt_out_capturing_by_default: true,  // wait for cookie consent
  });

  if (userId) {
    posthog.identify(userId);  // link events to user
  }
}

export function track(event: string, properties?: Record<string, unknown>) {
  posthog.capture(event, properties);
}

export function optIn()  { posthog.opt_in_capturing(); }
export function optOut() { posthog.opt_out_capturing(); }

// Usage — structured event names
track('user:invited',      { role: 'member' });
track('export:downloaded', { format: 'csv', rows: 1500 });
track('plan:upgraded',     { from: 'free', to: 'pro' });
track('feature:used',      { feature: 'bulk-export' });
```

```tsx
// App.tsx — init once
function App() {
  const { data } = useBootstrap();
  const { consent } = useCookieConsent();

  useEffect(() => {
    initAnalytics(data?.user?.id);
  }, [data?.user?.id]);

  // Apply consent from cookie banner
  useEffect(() => {
    if (consent?.analytics) optIn();
    else optOut();
  }, [consent?.analytics]);

  return <Router />;
}
```

### Feature usage tracking — auto via flags

```tsx
// Track when a feature flag is evaluated — know if flags are being used
export function useFlag(key: string): boolean {
  const enabled = useContext(FlagContext)[key] ?? false;

  useEffect(() => {
    track('feature_flag:evaluated', { flag: key, enabled });
  }, [key, enabled]);

  return enabled;
}
```
