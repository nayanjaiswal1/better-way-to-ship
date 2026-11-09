# Node Package Best Practices

## Naming & Structure
- Scope your package (`@org/pkg`) to avoid name collisions
- Keep source in `src/`, build output in `dist/` — never publish `src/`
- Use a single entry point unless you have clear sub-path reasons

## `package.json` Essentials
- Set `"main"`, `"module"`, and `"exports"` correctly for CJS/ESM consumers
- Set `"files"` to allowlist only what belongs in the published package (`dist`, `README`, `LICENSE`)
- Pin `"engines"` to the minimum supported Node version
- Set `"sideEffects": false` if the package is tree-shakeable

## Versioning
- Follow [SemVer](https://semver.org): `MAJOR.MINOR.PATCH`
- Use [Changesets](https://github.com/changesets/changesets) for versioning and changelog generation
- Never manually edit `CHANGELOG.md` — let Changesets own it

## TypeScript
- Ship declaration files (`.d.ts`) alongside JS output
- Set `"declaration": true` and `"declarationMap": true` in `tsconfig.json`
- Expose types via the `"types"` field in `package.json`

## Testing
- Use `vitest` for unit tests; keep tests co-located or in `tests/`
- Test the built output (not raw source) before publishing

## Releasing
- Run `pnpm build && pnpm test` before every release
- Use `pnpm publish --access public` (or `--access restricted` for scoped private packages)
- Use provenance attestation (`--provenance`) for supply-chain transparency

## CI Essentials
- Lint: `eslint`
- Format: `prettier`
- Type-check: `tsc --noEmit`
- Test on the minimum and latest supported Node LTS versions
