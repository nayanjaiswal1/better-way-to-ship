# TypeScript Advanced Patterns

## Utility Types

Built-in TypeScript utilities — never rewrite what already exists.

```tsx
interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'member' | 'viewer';
  createdAt: string;
  tenantId: string;
}

// Pick — only the fields you need
type UserPreview = Pick<User, 'id' | 'name' | 'role'>;

// Omit — everything except sensitive fields
type PublicUser = Omit<User, 'tenantId'>;

// Partial — all fields optional (for PATCH payloads)
type UserUpdate = Partial<Pick<User, 'name' | 'email'>>;

// Required — make all optional fields required
type CompleteUser = Required<User>;

// Record — typed object map
type RolePermissions = Record<User['role'], string[]>;
// { admin: [...], member: [...], viewer: [...] }

// ReturnType — infer function return type
const fetchUser = async (id: string) => ({ id, name: 'John' });
type FetchedUser = Awaited<ReturnType<typeof fetchUser>>;

// Parameters — infer function params
type FetchUserParams = Parameters<typeof fetchUser>;
// [id: string]

// Extract / Exclude — filter union types
type AdminOrMember = Extract<User['role'], 'admin' | 'member'>;
// 'admin' | 'member'

type NonAdmin = Exclude<User['role'], 'admin'>;
// 'member' | 'viewer'
```

---

## Discriminated Unions

Model state exhaustively — compiler catches missing cases.

```tsx
// ✅ Discriminated union — type narrows automatically
type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: string };

function UserDisplay({ state }: { state: AsyncState<User> }) {
  switch (state.status) {
    case 'idle':    return null;
    case 'loading': return <Skeleton />;
    case 'success': return <div>{state.data.name}</div>;  // data is typed here
    case 'error':   return <div>{state.error}</div>;      // error is typed here
    // TypeScript errors if you miss a case
  }
}

// API response types — discriminated by success/error
type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: { code: string; message: string } };

async function fetchUser(id: string): Promise<ApiResult<User>> {
  const res = await fetch(`/api/v1/users/${id}`, { credentials: 'include' });
  if (!res.ok) return { ok: false, error: await res.json() };
  return { ok: true, data: await res.json() };
}

// Usage — exhaustive handling
const result = await fetchUser(id);
if (result.ok) {
  console.log(result.data.name);  // ✅ typed
} else {
  console.error(result.error.message);  // ✅ typed
}
```

---

## Generic Components

Write once, work with any type — the React equivalent of TypeScript generics.

```tsx
// Generic list component — works for any data type
interface Column<T> {
  key: keyof T;
  label: string;
  render?: (value: T[keyof T], row: T) => React.ReactNode;
}

interface DataTableProps<T extends { id: string | number }> {
  rows: T[];
  columns: Column<T>[];
  onRowClick?: (row: T) => void;
}

function DataTable<T extends { id: string | number }>({
  rows,
  columns,
  onRowClick,
}: DataTableProps<T>) {
  return (
    <table>
      <thead>
        <tr>{columns.map(col => <th key={String(col.key)}>{col.label}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map(row => (
          <tr key={row.id} onClick={() => onRowClick?.(row)}>
            {columns.map(col => (
              <td key={String(col.key)}>
                {col.render
                  ? col.render(row[col.key], row)
                  : String(row[col.key])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Usage — fully typed
<DataTable<User>
  rows={users}
  columns={[
    { key: 'name', label: 'Name' },
    { key: 'email', label: 'Email' },
    { key: 'role', label: 'Role', render: (role) => <Badge>{role}</Badge> },
  ]}
  onRowClick={(user) => navigate(`/users/${user.id}`)}
/>
```

```tsx
// Generic Select — typed options
interface SelectProps<T> {
  options: T[];
  value: T | null;
  onChange: (value: T) => void;
  getLabel: (option: T) => string;
  getValue: (option: T) => string | number;
}

function Select<T>({ options, value, onChange, getLabel, getValue }: SelectProps<T>) {
  return (
    <select
      value={value ? String(getValue(value)) : ''}
      onChange={e => {
        const selected = options.find(o => String(getValue(o)) === e.target.value);
        if (selected) onChange(selected);
      }}
    >
      {options.map(option => (
        <option key={String(getValue(option))} value={String(getValue(option))}>
          {getLabel(option)}
        </option>
      ))}
    </select>
  );
}

// Usage
<Select<User>
  options={users}
  value={selectedUser}
  onChange={setSelectedUser}
  getLabel={(u) => u.name}
  getValue={(u) => u.id}
/>
```

---

## Template Literal Types

Type-safe event names, route paths, CSS classes.

```tsx
// Type-safe event system
type ResourceType = 'user' | 'post' | 'order';
type Action = 'created' | 'updated' | 'deleted';
type EventName = `${ResourceType}.${Action}`;
// 'user.created' | 'user.updated' | 'user.deleted' | 'post.created' | ...

function subscribe(event: EventName, handler: (data: unknown) => void) {
  // TypeScript prevents typos like 'usr.created'
}
subscribe('user.created', handler);  // ✅
subscribe('usr.created', handler);   // ❌ TypeScript error

// Type-safe API routes
type ApiVersion = 'v1' | 'v2';
type ApiPath = `/${ApiVersion}/${string}`;

function apiFetch(path: ApiPath) {
  return fetch(path, { credentials: 'include' });
}
apiFetch('/v1/users');   // ✅
apiFetch('/users');      // ❌ TypeScript error
```

---

## Accessibility Testing (axe-core)

Automated a11y checks in unit tests and CI.

```bash
npm install --save-dev @axe-core/react axe-core vitest-axe
```

```tsx
// tests/setup.ts
import { configureAxe } from 'vitest-axe';
import 'vitest-axe/extend-expect';

configureAxe({
  rules: [
    { id: 'region', enabled: false },  // disable if not applicable
  ],
});

// components/Button.test.tsx
import { render } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { Button } from './Button';

describe('Button', () => {
  it('should have no a11y violations', async () => {
    const { container } = render(<Button onClick={() => {}}>Save</Button>);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should have no a11y violations when disabled', async () => {
    const { container } = render(<Button disabled>Save</Button>);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// Page-level a11y test
describe('UsersPage', () => {
  it('should have no a11y violations', async () => {
    const { container } = render(
      <QueryClientProvider client={createTestQueryClient()}>
        <UsersPage />
      </QueryClientProvider>
    );
    await waitFor(() => screen.getByRole('table'));
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
```

```yaml
# CI — run a11y tests on every PR
# Already runs with: npm run test
# Ensure test:ci script includes axe tests
```

---

## Strict TypeScript Config

```json
// tsconfig.json
{
  "compilerOptions": {
    "strict": true,                      // enables all strict checks
    "noUncheckedIndexedAccess": true,    // arr[0] is T | undefined, not T
    "exactOptionalPropertyTypes": true,  // { a?: string } ≠ { a: string | undefined }
    "noImplicitReturns": true,           // all code paths must return
    "noFallthroughCasesInSwitch": true,  // no accidental switch fallthrough
    "forceConsistentCasingInFileNames": true
  }
}
```
