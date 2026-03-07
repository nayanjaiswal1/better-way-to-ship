---
description: Testing standards and patterns
globs: "**/*.test.tsx,**/*.test.ts,tests/**"
alwaysApply: false
---

# Testing Rules

## Framework
- Vitest 4 + @testing-library/react
- Always import from `vitest`: `import { describe, it, expect, vi } from "vitest"`
- Use `render`, `screen`, `userEvent` from Testing Library

## Patterns
- Arrange → Act → Assert structure
- Use `userEvent` (async) over `fireEvent` for user interactions
- Prefer `getByRole` > `getByLabelText` > `getByTestId`
- Mock only at module boundaries, not internal functions
- Use `vi.mock()` for external modules

## Coverage
- Minimum 80% lines, functions, branches, statements
- Critical paths need 100% branch coverage
