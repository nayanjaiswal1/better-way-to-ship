# Monorepo — Turborepo

Manage frontend + backend + shared packages in one repo with fast incremental builds.

## Structure

```
myapp/
├── apps/
│   ├── web/                   # React frontend (Vite)
│   │   ├── src/
│   │   ├── package.json
│   │   └── vite.config.ts
│   ├── api/                   # FastAPI or Django backend
│   │   ├── app/
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   └── docs/                  # Storybook / documentation site
│       └── package.json
├── packages/
│   ├── ui/                    # Shared React component library
│   │   ├── src/
│   │   └── package.json
│   ├── types/                 # Shared TypeScript types (generated from OpenAPI)
│   │   ├── src/
│   │   └── package.json
│   └── config/                # Shared configs (ESLint, TypeScript, Prettier)
│       ├── eslint/
│       ├── typescript/
│       └── package.json
├── turbo.json
├── package.json               # root workspace
└── pnpm-workspace.yaml
```

---

## Setup

```bash
# Use pnpm — faster than npm, native workspace support
npm install -g pnpm

# Create workspace
pnpm init
pnpm add turbo --save-dev --workspace-root
```

```yaml
# pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/*"
```

```json
// package.json (root)
{
  "name": "myapp",
  "private": true,
  "scripts": {
    "dev":     "turbo run dev",
    "build":   "turbo run build",
    "test":    "turbo run test",
    "lint":    "turbo run lint",
    "type-check": "turbo run type-check",
    "clean":   "turbo run clean && rm -rf node_modules"
  },
  "devDependencies": {
    "turbo": "^2.0.0"
  },
  "engines": {
    "node": ">=20",
    "pnpm": ">=9"
  }
}
```

---

## Turborepo Pipeline

```json
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "ui": "tui",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],   // build dependencies first (packages/* before apps/*)
      "outputs": [".next/**", "dist/**", "build/**", ".turbo/**"],
      "env": ["NODE_ENV", "VITE_API_URL"]
    },
    "dev": {
      "cache": false,            // never cache dev servers
      "persistent": true         // long-running process
    },
    "test": {
      "dependsOn": ["^build"],
      "outputs": ["coverage/**"],
      "env": ["NODE_ENV"]
    },
    "lint": {
      "outputs": []
    },
    "type-check": {
      "dependsOn": ["^build"],   // needs package types built first
      "outputs": []
    },
    "clean": {
      "cache": false
    }
  },
  "globalEnv": ["CI", "TURBO_TOKEN", "TURBO_TEAM"]
}
```

---

## Shared UI Package

```json
// packages/ui/package.json
{
  "name": "@myapp/ui",
  "version": "0.0.0",
  "private": true,
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts"
  },
  "scripts": {
    "lint":       "eslint src/",
    "type-check": "tsc --noEmit"
  },
  "peerDependencies": {
    "react": "^18",
    "react-dom": "^18"
  },
  "devDependencies": {
    "@myapp/config": "workspace:*",
    "typescript": "^5"
  }
}
```

```tsx
// packages/ui/src/index.ts — export all shared components
export { Button }    from "./components/Button";
export { Badge }     from "./components/Badge";
export { Modal }     from "./components/Modal";
export { DataTable } from "./components/DataTable";
export { Input }     from "./components/Input";
export * from "./hooks/useDebounce";
export * from "./hooks/useLocalStorage";
```

```json
// apps/web/package.json — consume shared UI
{
  "name": "@myapp/web",
  "dependencies": {
    "@myapp/ui":    "workspace:*",
    "@myapp/types": "workspace:*"
  }
}
```

```tsx
// apps/web/src/features/users/UserCard.tsx
import { Badge, Button } from "@myapp/ui";
import type { User } from "@myapp/types";
```

---

## Shared Types Package

```json
// packages/types/package.json
{
  "name": "@myapp/types",
  "version": "0.0.0",
  "private": true,
  "main": "./src/index.ts",
  "scripts": {
    "generate": "openapi-typescript http://localhost:8000/openapi.json -o src/api.d.ts",
    "build":    "tsc --noEmit",
    "type-check": "tsc --noEmit"
  }
}
```

```ts
// packages/types/src/index.ts
export type { components, paths } from "./api.d.ts";   // generated from OpenAPI

// Shared domain types
export interface PaginatedResponse<T> {
  data:       T[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
}

export interface ApiError {
  error: { code: string; message: string; status: number };
}
```

---

## Shared Config Package

```json
// packages/config/package.json
{
  "name": "@myapp/config",
  "version": "0.0.0",
  "private": true,
  "exports": {
    "./eslint":      "./eslint/index.js",
    "./typescript":  "./typescript/base.json",
    "./prettier":    "./prettier/index.js"
  }
}
```

```js
// packages/config/eslint/index.js
module.exports = {
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
  ],
  rules: {
    "no-console": ["warn", { allow: ["warn", "error"] }],
    "@typescript-eslint/no-explicit-any": "error",
  },
};
```

```json
// packages/config/typescript/base.json
{
  "compilerOptions": {
    "target":          "ES2022",
    "module":          "ESNext",
    "moduleResolution": "bundler",
    "strict":          true,
    "skipLibCheck":    true,
    "declaration":     true,
    "declarationMap":  true,
    "sourceMap":       true
  }
}
```

```json
// apps/web/tsconfig.json — extends shared config
{
  "extends": "@myapp/config/typescript",
  "compilerOptions": {
    "outDir": "dist",
    "paths": {
      "@myapp/ui":    ["../../packages/ui/src"],
      "@myapp/types": ["../../packages/types/src"]
    }
  },
  "include": ["src"]
}
```

---

## Remote Caching — Vercel / Self-Hosted

Share build cache across CI runners and developer machines. Run a task once, never again.

```bash
# Vercel Remote Cache (free for open source, paid for teams)
npx turbo login
npx turbo link   # link to your Vercel team

# Self-hosted with Ducktape (open source)
docker run -p 3000:3000 ducktape/cache-server
```

```json
// turbo.json — point to self-hosted cache
{
  "remoteCache": {
    "apiUrl": "https://cache.internal.example.com"
  }
}
```

```bash
# CI — set env vars for remote caching
export TURBO_TOKEN="your-token"
export TURBO_TEAM="your-team"

turbo build   # downloads cache if available, skips build entirely
```

---

## CI — Affected Packages Only

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history for change detection

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      # Turbo only runs tasks for changed packages + their dependents
      - run: pnpm turbo build test lint type-check
        env:
          TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
          TURBO_TEAM:  ${{ secrets.TURBO_TEAM }}

  # Backend is separate — Python doesn't use Turborepo
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/api
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install uv && uv sync
      - run: pytest --cov --cov-fail-under=80
```

---

## Dev Workflow

```bash
# Run everything at once (Turborepo starts in parallel)
pnpm dev

# Run only web
pnpm --filter @myapp/web dev

# Run only affected by changes
pnpm turbo build --filter=...[HEAD^1]

# Add a package to a specific workspace
pnpm --filter @myapp/web add react-query

# Add shared package
pnpm --filter @myapp/web add @myapp/ui

# Run a script in all workspaces
pnpm -r run lint
```

---

## Makefile — Top-Level Commands

```makefile
# Makefile (root)
.PHONY: dev build test lint install clean

install:
	pnpm install

dev:
	pnpm dev &                              # frontend + packages
	cd apps/api && make dev                 # backend

build:
	pnpm turbo build

test:
	pnpm turbo test                         # JS tests
	cd apps/api && pytest --cov            # Python tests

lint:
	pnpm turbo lint
	cd apps/api && ruff check .

type-check:
	pnpm turbo type-check

api:types:
	cd packages/types && pnpm generate     # regenerate from OpenAPI

clean:
	pnpm turbo clean
	pnpm store prune
```

---

## Monorepo Checklist

- [ ] `pnpm` workspaces — not npm/yarn (better performance + disk dedup)
- [ ] `@myapp/ui` shared component library — no copy-pasting components
- [ ] `@myapp/types` generated from OpenAPI — single source of truth
- [ ] `@myapp/config` shared ESLint + TypeScript + Prettier configs
- [ ] `turbo.json` pipeline with correct `dependsOn` — packages build before apps
- [ ] Remote cache configured — CI hits cache, skips redundant builds
- [ ] `--filter=...[HEAD^1]` in CI — only build/test affected packages
- [ ] `dev` task marked `persistent: true, cache: false` — never cached
- [ ] Backend (Python) in `apps/api/` but managed separately — not in Turbo pipeline
- [ ] `pnpm --frozen-lockfile` in CI — deterministic installs
