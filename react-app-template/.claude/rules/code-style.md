---
description: TypeScript and React code style rules
alwaysApply: true
---

# Code Style

## TypeScript
- Prefer `interface` over `type` for object shapes
- Use `const` assertions for literal objects: `as const`
- Destructure props at function signature, never inside body
- Explicit return types on all exported functions

## React
- Functional components only — no class components
- Custom hooks prefix: `use` (e.g., `useAuth`, `useData`)
- Props interface named `<ComponentName>Props`
- Avoid useEffect for derived state — compute inline

## Imports order (enforced by eslint import/order)
1. Node builtins
2. External packages
3. Internal (`@/`)
4. Relative (`./`, `../`)
