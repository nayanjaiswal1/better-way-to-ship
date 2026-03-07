# Node Package Template

Production-ready Node.js/TypeScript package template with dual ESM/CJS output, strict quality gates, and automated npm publishing via Changesets.

## Stack

| Tool | Purpose |
|---|---|
| TypeScript 5 (strict) | Type-safe source |
| tsup | Zero-config dual ESM + CJS build |
| Vitest | Fast unit testing |
| ESLint (TypeScript strict) | Linting |
| Prettier | Code formatting |
| Husky + lint-staged | Pre-commit enforcement |
| commitlint | Conventional commit validation |
| Changesets | Versioning and changelog management |
| GitHub Actions | CI + automated npm publish |

## Repository Structure

```
node-package-template/
├── .changeset/
│   └── config.json         # Changesets configuration
├── .github/
│   └── workflows/
│       └── ci.yml          # Quality, multi-node tests, build, release
├── .husky/
│   ├── pre-commit
│   └── commit-msg
├── src/
│   └── index.ts            # Public API export surface
├── tests/
│   └── index.test.ts
├── commitlint.config.cjs
├── .eslintrc.cjs
├── .prettierrc
├── package.json
├── tsconfig.json
├── tsconfig.test.json
├── tsup.config.ts
└── vitest.config.ts
```

## Engineering Standards

- **Dual publish** (ESM + CJS) with `exports` map — supports both module systems
- **`verbatimModuleSyntax`** — enforces correct `import type` usage
- **TypeScript strict** with `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`
- **`sideEffects: false`** — enables tree-shaking in bundlers
- **NPM provenance** — published with `NPM_CONFIG_PROVENANCE=true` for supply-chain integrity
- **Coverage thresholds**: 90% lines/functions/statements, 85% branches
- **Multi-node matrix**: Node 20 and Node 22

## Developer Workflow

```bash
# Install dependencies
pnpm install

# Type check
pnpm typecheck

# Lint
pnpm lint

# Format
pnpm format

# Test
pnpm test

# Test with coverage
pnpm test:coverage

# Build (ESM + CJS + .d.ts)
pnpm build

# Watch mode
pnpm dev
```

## Quality Gates (CI)

| Job | Checks |
|---|---|
| `quality` | TypeScript, ESLint, Prettier |
| `test (Node 20)` | Vitest + coverage >= 90%, Codecov upload |
| `test (Node 22)` | Vitest (no coverage re-upload) |
| `build` | tsup build + CJS smoke test |
| `release` | Changesets PR or npm publish |

## Release Workflow

This template uses [Changesets](https://github.com/changesets/changesets) for versioning:

1. After merging a feature, add a changeset:
   ```bash
   pnpm changeset
   ```
2. Commit the generated `.changeset/*.md` file
3. Push to `main` — CI creates a "Release PR" that bumps `package.json` version and updates `CHANGELOG.md`
4. Merging the Release PR publishes to npm automatically with provenance

Set `NPM_TOKEN` in GitHub repository secrets before the first publish.
