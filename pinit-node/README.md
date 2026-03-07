# create-pinit

Scaffold production-ready Node/React projects in one command. No copying, no manual setup.

## Usage

```bash
# no install needed
npx create-pinit react my-app
npx create-pinit nodepkg my-lib

# or install globally
npm install -g create-pinit
create-pinit react my-app
```

## Templates

| Template | Stack |
|---|---|
| `react` | React 19 + Vite 7 + TypeScript 5.8 + Vitest 4 + ESLint 9 flat config |
| `nodepkg` | Node package with tsdown, Vitest 4, Changesets, ESLint 9 flat config |

## What you get

Every scaffolded project includes:

- **pnpm 10** for dependency management
- **ESLint 9** flat config (`eslint.config.ts`) + **Prettier 3**
- **TypeScript 5.8** strict — `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`
- **Vitest 4** with 80–90% coverage thresholds
- **Husky** commit-msg hook — strips and blocks AI agent attribution lines
- **commitlint** with conventional commit rules + `no-agent-detail` plugin
- **GitHub Actions CI** and **GitLab CI** pipelines
- **VS Code settings** — format on save, ESLint flat config, correct extensions
- **Dev container** — `devcontainer.json` for Codespaces or local container
- **AI agent rules** — `CLAUDE.md`, `.claude/rules/`, `.cursor/rules/` pre-filled

## After scaffolding

```bash
cd my-app
pnpm install
pnpm dev       # react: start dev server
pnpm test      # all tests pass out of the box
```
