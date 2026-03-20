# React Best Practices

## Architecture & Structure
- **Feature-based folder structure** over type-based (group by feature, not by `components/`, `hooks/`)
- **Colocation** - keep files close to where they're used
- **Barrel exports** (`index.ts`) for clean public APIs per module — note: can impact tree-shaking and bundle size, use judiciously
- Use **monorepo** for large apps (Turborepo, Nx)
- **Named exports** - avoid default exports where avoidable
- Max **200 lines** per file

## State Management
- **React Context + useReducer** for simple global state
- **TanStack Query (React Query)** for server state - handles caching, refetching, loading states
- **Zustand** or **Jotai** for complex client state (simpler than Redux)
- **Lift state up** only when needed - keep state as local as possible
- **Avoid useState overuse** - prefer derived state, URL state, or server state

## Performance
- **Code splitting** with `React.lazy()` and `Suspense`
- **Memoization** wisely - `useMemo`, `useCallback`, `React.memo`
- **Virtualization** for long lists (react-window, react-virtual)
- **Avoid anonymous functions** in render - they're new objects each render
- Use **production build** (`npm run build`) - dev bundle is 3-4x larger

## Data Fetching & API Optimization
- Handle **loading and error states** explicitly
- **Cancel in-flight requests** on unmount/abort (AbortController)
- Use **stale-while-revalidate** pattern (React Query does this)
- **Prefetch** data for likely navigation
- **Batch API requests** - combine multiple queries into single call
- **Avoid waterfall requests** - use parallel queries with Promise.all
- Configure **staleTime** in queryClient defaults for aggressive caching
- Implement **infinite queries** for pagination instead of page-based

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,    // 5 minutes
      gcTime: 1000 * 60 * 30,      // 30 minutes (formerly cacheTime)
      retry: 3,
      refetchOnWindowFocus: false,
    },
  },
});

// Parallel queries - avoid waterfalls
const [users, roles] = await Promise.all([
  queryClient.fetchQuery({ queryKey: ['users'], queryFn: fetchUsers }),
  queryClient.fetchQuery({ queryKey: ['roles'], queryFn: fetchRoles }),
]);
```

## Forms (React Hook Form + Zod)
- Use **server-generated schemas** for validation
- **Client-side validation** mirrors backend rules
- Never hardcode form field definitions in UI
- Handle **dependent fields** via `useWatch` or computed values in render

```tsx
import { useForm, useWatch } from 'react-hook-form';

// ANTI-PATTERN: watch + useEffect causes infinite re-renders
// ❌ DON'T do this:
const { watch } = useForm();
const watchedValue = watch('field');
React.useEffect(() => {
  if (watchedValue) {
    // This triggers re-render, which causes watch to fire again
    setOptions(/*...*/);
  }
}, [watchedValue]);

// ✅ CORRECT: Use useWatch for derived values
const { control } = useForm();
const watchedValue = useWatch({ control, name: 'field' });
const options = useMemo(() => {
  return computeOptions(watchedValue);
}, [watchedValue]);
```

**Note**: The `deps` option is only available on `trigger()`, not `register()`. For dependent field logic, use `useWatch` or computed values instead.

## Error Handling
- Implement **error boundaries** to catch React component errors
- Handle API errors gracefully with user-friendly messages
- Never expose internal error details to users

```tsx
import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? <div>Something went wrong</div>;
    }
    return this.props.children;
  }
}

// Usage
<ErrorBoundary>
  <Dashboard />
</ErrorBoundary>
```

## Components
- **Composition over inheritance**
- **Single responsibility** - one component, one purpose
- **Custom hooks** to extract reusable logic
- Use **TypeScript** for type safety

## Server-Driven UI — Never Hardcode These

Following the **"write once, never touch"** principle, all of the following must come from the backend — never hardcoded in the UI.

### Navigation / Sidebar
```tsx
// ❌ Never do this
const navItems = [
  { label: 'Users', path: '/users' },
  { label: 'Admin', path: '/admin' },  // who sees this? hardcoded!
]

// ✅ Backend-driven — write once, never touch
function Sidebar() {
  const { data } = useQuery({
    queryKey: ['navigation'],
    queryFn: () => fetch('/api/meta/navigation', { credentials: 'include' }).then(r => r.json()),
  });

  return (
    <nav>
      {data?.items.map(item => (
        <NavLink key={item.key} to={item.path}>{item.label}</NavLink>
      ))}
    </nav>
  );
}
```

### Dropdown / Select Options (Enums)
```tsx
// ❌ Never do this — duplicated from backend
const statusOptions = ['active', 'inactive', 'pending']

// ✅ Options come from FilterDef.options or form_schema
// Already handled by <FilterBar filters={meta.filters} /> and <DynamicForm schema={meta.form_schema} />
```

### Validation Rules
```tsx
// ❌ Never duplicate backend rules in frontend
const schema = z.object({
  age: z.number().min(18).max(100),  // what if backend changes this?
})

// ✅ Generate Zod schema from backend's form_schema (JSON Schema)
import { zodFromJsonSchema } from 'zod-from-json-schema';  // or equivalent

function useFormSchema(endpoint: string) {
  const { data } = useQuery({
    queryKey: ['schema', endpoint],
    queryFn: () => fetch(endpoint, { credentials: 'include' }).then(r => r.json()),
  });
  return data?.meta.form_schema ? zodFromJsonSchema(data.meta.form_schema) : null;
}
```

### Status Badge Colors / Labels
```tsx
// ❌ Never do this
const badgeColors: Record<string, string> = {
  active: 'green',
  inactive: 'red',
  pending: 'yellow',
}

// ✅ Comes from ColumnDef.render_options — write Badge renderer once
function Badge({ value, renderOptions }: { value: string; renderOptions?: Record<string, string> }) {
  const color = renderOptions?.[value] ?? 'gray';
  return <span className={`badge badge-${color}`}>{value}</span>;
}

// Used in DataTable — driven by meta.columns[].render_options
```

### Row / Bulk Actions
```tsx
// ❌ Never do this
<BulkActions>
  <button onClick={handleDelete}>Delete</button>   {/* who can delete? hardcoded! */}
  <button onClick={handleExport}>Export</button>
</BulkActions>

// ✅ Actions come from meta.actions
function ActionBar({ actions, selectedIds }: { actions: ActionDef[]; selectedIds: number[] }) {
  const bulk = actions.filter(a => a.bulk);
  const row = actions.filter(a => !a.bulk);

  return (
    <div>
      {bulk.map(action => (
        <button
          key={action.key}
          className={action.variant}
          onClick={() => handleAction(action.key, selectedIds)}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}
```

### Dashboard Widgets / Layout
```tsx
// ❌ Never do this
{user.role === 'admin' && <RevenueWidget />}   {/* role check in UI! */}
{user.role === 'manager' && <TeamWidget />}

// ✅ Backend returns widget list for the current user — write renderers once
function Dashboard() {
  const { data } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => fetch('/api/meta/dashboard', { credentials: 'include' }).then(r => r.json()),
  });

  return (
    <div className="dashboard-grid">
      {data?.meta.widgets.map(widget => (
        <Widget key={widget.type} type={widget.type} title={widget.title} config={widget.config} />
      ))}
    </div>
  );
}

// Widget renderer — write once
const widgetRegistry: Record<string, React.ComponentType<{ config: any }>> = {
  stat: StatWidget,
  chart: ChartWidget,
  table: TableWidget,
};

function Widget({ type, title, config }: WidgetDef) {
  const Component = widgetRegistry[type];
  if (!Component) return null;
  return (
    <div className="widget">
      <h3>{title}</h3>
      <Component config={config} />
    </div>
  );
}
```

### The Pattern — Write Generic Renderers Once

| What | Component | Driven by |
|------|-----------|-----------|
| Filters | `<FilterBar />` | `meta.filters` |
| Table columns | `<DataTable />` | `meta.columns` |
| Forms | `<DynamicForm />` | `meta.form_schema` |
| Permissions | inline checks | `meta.permissions` |
| Actions | `<ActionBar />` | `meta.actions` |
| Navigation | `<Sidebar />` | `meta.navigation` |
| Dashboard | `<Dashboard />` | `meta.widgets` |
| Badge colors | `<Badge />` | `meta.columns[].render_options` |

> Write each renderer **once**. All content and structure comes from the backend — no frontend code change needed when requirements change.

---

## Optimistic Updates

Update the UI instantly — revert only if the server rejects. Zero extra API calls, feels instant.

```tsx
// hooks/useUpdateUser.ts
import { useMutation, useQueryClient } from '@tanstack/react-query';

export function useUpdateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { id: number; name: string }) =>
      fetch(`/api/v1/users/${data.id}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).then(r => r.json()),

    onMutate: async (updated) => {
      // 1. Cancel in-flight refetches so they don't overwrite optimistic value
      await queryClient.cancelQueries({ queryKey: ['users', 'data'] });

      // 2. Snapshot current value for rollback
      const previous = queryClient.getQueryData(['users', 'data']);

      // 3. Optimistically update cache — UI updates instantly
      queryClient.setQueryData(['users', 'data'], (old: any) => ({
        ...old,
        data: old.data.map((u: any) =>
          u.id === updated.id ? { ...u, ...updated } : u
        ),
      }));

      return { previous };  // returned as context
    },

    onError: (_err, _updated, context) => {
      // Revert to snapshot on failure
      queryClient.setQueryData(['users', 'data'], context?.previous);
    },

    onSettled: () => {
      // Always refetch after mutation to sync with server
      queryClient.invalidateQueries({ queryKey: ['users', 'data'] });
    },
  });
}

// Usage
function UserRow({ user }: { user: User }) {
  const { mutate: updateUser } = useUpdateUser();

  return (
    <input
      defaultValue={user.name}
      onBlur={(e) => updateUser({ id: user.id, name: e.target.value })}
    />
  );
}
```

## Bundle Optimization

### Analyze bundle size
```bash
# Vite
npx vite-bundle-analyzer
# Or with rollup plugin
npm install --save-dev rollup-plugin-visualizer
```

### Dynamic imports — split at route level
```tsx
// ❌ All pages bundled together
import { AdminPage } from './pages/AdminPage';

// ✅ Each route is a separate chunk — loaded on demand
const AdminPage = React.lazy(() => import('./pages/AdminPage'));
const UsersPage = React.lazy(() => import('./pages/UsersPage'));

function Router() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/users" element={<UsersPage />} />
      </Routes>
    </Suspense>
  );
}
```

### Tree shaking — import only what you use
```tsx
// ❌ Imports entire library
import _ from 'lodash';
const result = _.groupBy(items, 'status');

// ✅ Imports only one function
import groupBy from 'lodash/groupBy';
const result = groupBy(items, 'status');
```

### Verify tree shaking works
```bash
# Check if unused exports are being included
npx vite build --mode production
# Look for unexpectedly large chunks in the output
```

---

## Production Checklist
- **Monitor Core Web Vitals** (LCP, INP, CLS)
- Implement **error boundaries** for component error recovery
- Implement **debounced validation** for remote validation
- See [security.md](./security.md) for: CSP headers, dependency scanning
- See [devops.md](./devops.md) for: compression, CDN, cache headers

---

## React Checklist

### Security
- [ ] JWT in httpOnly cookies (see [security.md](./security.md) for implementation)
- [ ] CSP (Content Security Policy) headers — configured at web server/reverse proxy level, not React
- [ ] No secrets in client code
- [ ] XSS prevention — sanitize user input, use React's built-in escaping
- [ ] SameSite=Strict cookies (inherently prevents CSRF for browser-initiated requests)

### Type Safety
- [ ] OpenAPI types auto-generated from backend
- [ ] Contract tests for API responses
- [ ] TypeScript strict mode

### Performance
- [ ] Code splitting (lazy/Suspense)
- [ ] React Query staleTime configured
- [ ] Prefetching on hover
- [ ] Infinite scroll with cursor pagination
- [ ] Virtualization for long lists

### Error Handling
- [ ] Error boundaries wrapping major page sections
- [ ] User-friendly error messages (no raw stack traces)
- [ ] API errors handled with toast/inline feedback
- [ ] 401 responses redirect to login

### Accessibility
- [ ] Semantic HTML elements (`<button>`, `<nav>`, `<main>`)
- [ ] All images have `alt` text
- [ ] Keyboard navigation works for interactive elements
- [ ] Color contrast meets WCAG AA (4.5:1 ratio)
- [ ] Form inputs have associated `<label>` elements
