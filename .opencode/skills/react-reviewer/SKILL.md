---
name: react-reviewer
description: Review React code for best practices - components, hooks, state management, performance, and TypeScript
license: MIT
compatibility: opencode
metadata:
  audience: frontend-developers
  framework: React
---

## When to Use

Use this skill when reviewing React code. Load with: `skill({ name: "react-reviewer" })`

## Review Checklist

### Component Design (see `best-practices/react.md`)
- Functional components with hooks only
- Proper component composition
- Reusable component patterns
- Single responsibility principle

### State Management (see `best-practices/react.md#state`)
- Local state with useState for UI state
- React Query/SWR for server state
- Context for shared state (not overused)
- Avoid prop drilling - use composition or context

### Performance (see `best-practices/react.md#performance`)
- React.memo for expensive components
- useMemo for expensive calculations
- useCallback for callbacks passed to children
- Virtualization for long lists
- Code splitting with lazy()

### TypeScript (see `best-practices/typescript-advanced.md`)
- Proper typing - avoid `any`
- Use utility types (Partial, Pick, Omit)
- Discriminated unions for states
- Generic components for reusability

### Forms & Validation (see `best-practices/react.md#forms`)
- React Hook Form or Formik
- Client-side validation
- Error messages displayed

### Error Handling (see `best-practices/react.md#error-handling`)
- Error boundaries for graceful failures
- Loading states
- Empty states

### Testing (see `best-practices/testing.md`)
- Vitest + React Testing Library
- Test behavior, not implementation
- Coverage 80%+

### Accessibility (see `best-practices/react.md`)
- Semantic HTML
- ARIA labels when needed
- Keyboard navigation
- Focus management

### Frontend Patterns (see `best-practices/frontend-patterns.md`)
- Dark mode/theming support
- Responsive design
- Compound components when appropriate

## Common Issues to Flag

### ❌ Avoid
- Class components (use hooks)
- `useEffect` for everything
- Inline arrow functions in JSX
- Calling APIs in render
- `any` types
- Mutating state directly

### ✅ Prefer
- Custom hooks for logic reuse
- `useMemo`/`useCallback` appropriately
- Server state libraries (React Query)
- TypeScript strict mode
- Error boundaries

## Example Output

```
## React Best Practices Review

### ✅ Passed
- Functional components with hooks
- Proper TypeScript types

### ⚠️ Issues
- **Performance**: Inline function in JSX causing re-renders
  Fix: Use useCallback
  See: best-practices/react.md#performance

- **State**: Prop drilling through 4+ levels
  Fix: Use Context or composition
  See: best-practices/react.md#state

### ❌ Critical
- **Type**: `any` type on API response
  Fix: Define proper interface
  See: best-practices/typescript-advanced.md
```
