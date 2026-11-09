# Why This Exists

Every project starts the same way. Before writing a single line of product code, you spend hours — sometimes days — setting up the same things:

- Install and configure a linter
- Wire up a formatter
- Set up CI that actually catches problems
- Add pre-commit hooks so bad code never reaches the repo
- Configure TypeScript strict mode (and fight with it)
- Figure out the right test runner config again
- Set up a dev container so the next person doesn't spend half a day on environment setup
- Add VS Code settings so the editor behaves consistently across the team
- Write a .gitignore from scratch (or copy-paste from somewhere random)
- Pick a commit convention and wonder if anyone will follow it

Then you do it again on the next project. And the one after that.

This repository exists to stop that cycle.

---

## What We Kept Repeating

These are the exact things that came up in every project without exception:

### Tooling setup
Every Python project needed uv, Ruff, MyPy, and pre-commit configured the same way. Every JS/TS project needed ESLint 9 flat config, Prettier, and the right tsconfig strict flags. Getting these right takes time — getting them *consistent* across projects takes even more.

### CI/CD boilerplate
GitHub Actions workflows for lint, test, and build are nearly identical across projects. The same goes for GitLab CI. Writing them from scratch every time introduces subtle differences and bugs.

### Commit discipline
Without enforcement, commit messages become useless ("fix stuff", "wip", "asdf"). Conventional Commits give structure, but only if you actually wire up commitlint or commitizen with hooks. That's non-trivial to set up correctly the first time.

### AI agent attribution pollution
When using AI coding assistants, commit messages often get stamped with `Co-Authored-By: Claude`, `Generated with Claude Code`, or similar lines. These attribution lines:
- Pollute the git history
- Reveal internal tooling to public repos
- Add noise to changelogs and release notes

Every template here blocks these automatically — both by stripping them in the commit-msg hook before validation, and by rejecting them if they survive stripping.

### Editor inconsistency
One developer uses tabs, another uses spaces. One has format-on-save, another doesn't. The `.vscode/settings.json` and `.vscode/extensions.json` files in each template enforce a consistent baseline without being opinionated beyond what's necessary.

### Dev container cold starts
"Works on my machine" is a waste of everyone's time. The devcontainer setup means any team member (or GitHub Codespaces) gets an identical environment with zero manual steps.

### AI agent context
When using Claude Code, Cursor, or similar tools, the agent needs to understand the project's conventions — what stack is in use, what patterns to follow, what to avoid. Without this, the agent gives generic advice that doesn't fit the project. The `CLAUDE.md`, `.claude/rules/`, and `.cursor/rules/` files solve this.

---

## The Templates

| Template | When to use it |
|---|---|
| `react-app-template` | Browser-facing React apps with TypeScript |
| `fastapi-template` | Async Python APIs with a database |
| `django-rest-template` | Python APIs where you want Django's batteries |
| `python-package-template` | Libraries published to PyPI |
| `node-package-template` | Libraries published to npm |

Each template is production-ready from the first commit — not a toy scaffold, but the actual structure a real project should have on day one.

---

## The Rule

Copy the template. Rename things. Start building.

Do not spend time on infrastructure that is already solved here.
