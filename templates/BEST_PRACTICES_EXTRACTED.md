# Engineering Excellence: Extracted Best Practices

A consolidated guide to the high-signal patterns, CI/CD optimizations, and architectural standards.

---

# PART 1: PYTHON / FASTAPI

## 1. Dependency Management
- **Use `uv`** — `uv pip install` for near-instant dependency resolution (10-100x faster than pip)
- **uv sync** — install all dependencies from pyproject.toml
- **Lock files** — always commit `uv.lock`

## 2. Code Quality
- **Ruff** — replace Black, Isort, Flake8, Bandit with Ruff (10-100x faster)
- **MyPy strict** — mandatory type checking; `type: ignore` is last resort
- **`from __future__ import annotations`** — in every Python file
- **Static typing** — all new code must have type hints

## 3. Logging
- **structlog** — use for structured JSON logging
- **Never use print()** — use logger.debug/info/warn/error
- **No f-strings in logs** — use lazy formatting: `logger.info("msg", key=value)`

## 4. Configuration
- **Pydantic Settings** — for all config via `.env`
- **get_settings()** — never use `os.environ` directly
- **Validate at startup** — fail fast if config is wrong

## 5. Database (SQLAlchemy 2.0)
- **Always async** — `asyncpg` driver, never sync calls
- **ORM vs Schemas** — separate classes, never conflate
- **Repository pattern** — queries in repositories, logic in services

## 6. API Design
- **Response model** — always declare explicitly
- **Dependency injection** — use FastAPI Depends
- **Error handling** — raise AppError subclasses, not HTTPException from services

## 7. Migrations (Alembic)
- **Auto-generate** — `alembic revision --autogenerate`
- **Review before apply** — never run without review
- **Never modify** applied migrations — create new ones
- **alembic check** — must pass before merge

## 8. Testing
- **pytest-asyncio** — auto mode: `asyncio_mode = "auto"`
- **httpx AsyncClient** — for endpoint tests
- **Override dependencies** — in conftest.py for rollback
- **80% coverage** — minimum threshold

## 9. Docker
- **Layer optimization** — combine apt-get commands, clean up
- **PYTHONUNBUFFERED=1** — for real-time logs
- **PYTHONDONTWRITEBYTECODE=1** — cleaner images
- **ARG for secrets** — pass tokens at build time

## 10. Docker Compose
- **Healthchecks** — use `pg_isready`, `condition: service_healthy`
- **Named volumes** — for persistent data
- **Same image** — different entrypoints for workers

---

# PART 2: JAVASCRIPT / REACT / NEXT.JS

## 1. Dependencies
- **pnpm** — never npm or yarn
- **Exact versions** — use exact in package.json

## 2. TypeScript Rules
- **Strict mode** — always on
- **No `any`** — use `unknown` and narrow properly
- **import type** — for type-only imports
- **Absolute imports** — use `@/` alias

## 3. React/Next.js
- **Server Components** — default, use 'use client' only when needed
- **Co-located tests** — `Component.test.tsx` next to component
- **TanStack Query** — for server state
- **React Hook Form + Zod** — for forms

## 4. Code Quality
- **No console.log** — use console.warn/error only
- **ESLint + Prettier** — always run before commit
- **No eslint-disable** — without justification

## 5. Component Guidelines
- **Named exports** — avoid default exports
- **Hooks in /hooks** — custom hooks separate
- **Types in /types** — shared types centralized
- **Small components** — max 400 lines

## 6. Testing (Vitest)
- **@testing-library/react** — for component tests
- **@testing-library/user-event** — for interactions
- **Test behavior** — not implementation
- **80% coverage** — minimum

## 7. Performance
- **Bundle splitting** — code-split routes
- **Lazy loading** — load on demand
- **Image optimization** — use Next.js Image
- **Memoization** — useMemo, useCallback wisely

---

# PART 3: DEVOPS & CI/CD

## 1. CI Performance
- **Pre-baked images** — Dockerfile.ci with dependencies pre-installed
- **Content-hash tagging** — rebuild only on Dockerfile.ci change
- **Cache intelligently** — `.ruff_cache`, `.mypy_cache`, `UV_CACHE_DIR`
- **Interruptible pipelines** — kill stale builds

## 2. Docker Best Practices
- **Layer optimization** — single RUN for apt-get + cleanup
- **Multi-stage builds** — smaller final image
- **.dockerignore** — exclude node_modules, .git

## 3. Docker Compose
- **Healthchecks** — `pg_isready` for postgres
- **depends_on condition** — wait for healthy services
- **Named volumes** — prevent data loss
- **Service separation** — same image, different commands

## 4. Pipeline Stages
1. **Lint/Type Check** — fast, catch basics
2. **Test** — unit + integration
3. **Build** — compile
4. **Deploy** — to environment

## 5. Reporting
- **JUnit XML** — for test results
- **Cobertura XML** — for coverage diffs

---

# PART 4: AI/LLM ENGINEERING

## 1. Maker-Checker Pattern
- **Separate generation** from validation
- **Self-healing loops** — feed checker suggestions back to generator
- **Confidence scores** — have AI rate its own outputs

## 2. Output Enforcement
- **Strict JSON** — command LLMs to return deterministic JSON
- **Schema validation** — Pydantic for structure
- **Retry logic** — with exponential backoff

## 3. Prompt Management
- **Separate files** — store prompts in `.txt` files
- **Version prompts** — track changes
- **No hardcoded** prompts in code

## 4. Cost Control
- **Rate limiting** — on AI endpoints
- **Caching** — generated content where possible
- **Token tracking** — log usage

## 5. Lazy Loading
- **Import heavy libs** (openai, langchain) only when needed
- **Environment variables** — for API keys, not hardcoded

---

# PART 5: ARCHITECTURE & SCALABILITY

## 1. Service Layer
- **Router** — HTTP only: parse request, call service, return response
- **Service** — business logic, no HTTP concerns
- **Repository** — all DB queries
- **Models** — ORM only

## 2. Caching
- **Tenant isolation** — include tenant in cache keys
- **Stampede protection** — atomic add as lock
- **Invalidation** — track keys in manifest
- **Version counters** — for structural data

## 3. Error Handling
- **Consistent format** — always return same error structure
- **Graceful degradation** — user-friendly messages
- **Log context** — user ID, request ID, correlation

## 4. Security
- **Never hardcode secrets** — use env vars
- **Validate inputs** — everywhere
- **Sanitize outputs** — prevent XSS
- **Parameterized queries** — prevent SQL injection

---

# PART 6: CODE QUALITY PRINCIPLES

## SOLID
- **S**ingle Responsibility
- **O**pen-Closed
- **L**iskov Substitution
- **I**nterface Segregation
- **D**ependency Inversion

## DRY
- Extract common logic
- Duplicate code is a bug

## KISS
- Simple > Clever
- Hard to explain = wrong

## YAGNI
- Don't build for tomorrow
- Solve today's problem

## Naming
- camelCase / snake_case — consistent
- PascalCase — classes/components
- UPPER_SNAKE_CASE — constants
- Describe what it *does*

## Magic Numbers
- NEVER use numbers directly
- Use named constants

---

# PART 7: VERSION CONTROL

## Branch Naming
- `feature/<id>-description`
- `fix/<id>-description`
- `hotfix/<id>-description`
- `refactor/<id>-description`

## Commit Format
```
<type>(<scope>): <description>

<body (optional)>
```
Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert

## PR Etiquette
- **Small PRs** — max 400 lines
- **Good description** — what, why, how
- **Screenshots** — for UI
- **Self-review** — before marking ready

---

# PART 8: TESTING

## Test Naming
- Describe behavior: `should return user when valid id`
- Pattern: `should_<expected>_when_<condition>`

## AAA Pattern
```
// Arrange
const user = createUser();

// Act
const result = getUser(user.id);

// Assert
expect(result).toBeDefined();
```

## What to Mock
- External APIs
- Databases
- Time (use fake timers)

## What NOT to Mock
- Built-in functions
- What you don't own

---

# PART 9: DOCUMENTATION

## README
- One-liner description
- Quick start (5 steps max)
- Prerequisites
- Environment variables
- Common commands

## API Docs
- OpenAPI/Swagger
- Request/response formats
- Error codes

## Onboarding
- Architecture diagram
- Key files guide
- Code ownership

---

# PART 10: SECURITY

## Never
- Hardcode secrets
- Trust user input
- Skip validation
- Expose sensitive data

## Always
- Validate all inputs
- Sanitize outputs
- Use parameterized queries
- Rate limit endpoints
- Use HTTPS
