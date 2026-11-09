# React Application Template

Production-ready React application template with TypeScript, strict quality gates, and automated CI/CD.

## Stack

| Tool | Purpose |
|---|---|
| React 18 + TypeScript | UI framework with strict type safety |
| Vite | Build tool and dev server |
| Vitest + Testing Library | Unit and component testing |
| ESLint (flat config) | Linting with TypeScript, React, a11y, import rules |
| Prettier | Opinionated code formatting |
| Husky + lint-staged | Pre-commit quality enforcement |
| commitlint | Conventional commit message validation |
| GitHub Actions | CI/CD pipeline |

## Repository Structure

```
react-app-template/
├── .github/
│   └── workflows/
│       ├── ci.yml          # Quality gates, tests, build
│       └── release.yml     # Tag-triggered GitHub release
├── .husky/
│   ├── pre-commit          # Runs lint-staged
│   └── commit-msg          # Validates commit message
├── src/                    # Application source (TypeScript)
│   ├── main.tsx            # Entry point
│   ├── App.tsx             # Root component
│   ├── index.css           # Global styles
│   └── vite-env.d.ts       # Vite type declarations
├── tests/
│   └── setup.ts            # Vitest global setup
├── commitlint.config.js
├── eslint.config.js
├── index.html
├── package.json
├── .prettierrc
├── tsconfig.json
└── vite.config.ts
```

## Engineering Standards

- **TypeScript strict mode** with `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`
- **ESLint** enforces strict TypeScript, React hooks rules, accessibility (jsx-a11y), import ordering
- **Prettier** enforces consistent formatting, integrated with ESLint via `eslint-config-prettier`
- **Conventional Commits** enforced at commit time via commitlint
- **Coverage thresholds**: 80% lines, functions, branches, statements
- **Zero lint warnings** permitted in CI (`--max-warnings 0`)

## Developer Workflow

```bash
# Install dependencies
pnpm install

# Start dev server
pnpm dev

# Type check
pnpm typecheck

# Lint
pnpm lint

# Format
pnpm format

# Run tests
pnpm test

# Run tests with coverage
pnpm test:coverage

# Production build
pnpm build
```

## Quality Gates

All gates run automatically on `push` and `pull_request` to `main`/`develop`:

1. **Type check** — `tsc --noEmit`
2. **Lint** — ESLint with zero warnings
3. **Format check** — Prettier diff
4. **Tests + Coverage** — Vitest with 80% thresholds
5. **Build** — Vite production build

Pre-commit hooks enforce lint-staged (ESLint + Prettier on staged files) and commitlint on every commit locally.

## CI Behavior

- `quality` and `test` jobs run in parallel
- `build` job requires both to pass
- Coverage uploaded to Codecov
- Build artifact retained for 7 days

## Release Workflow

Push a semver tag to trigger a GitHub release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The release pipeline builds the app and attaches `dist/` artifacts with auto-generated release notes from conventional commits.
