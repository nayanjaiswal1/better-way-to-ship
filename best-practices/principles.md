# Principles & Shared Practices

## Shared Best Practices

| Concern     | React                      | FastAPI                          |
| ----------- | -------------------------- | -------------------------------- |
| Type Safety | TypeScript strict mode      | Pydantic v2 + MyPy strict        |
| Type Sharing| openapi-typescript          | OpenAPI schema auto-generation    |
| Testing     | Vitest + RTL               | pytest + pytest-asyncio           |
| Linting     | ESLint 9 + Prettier        | Ruff + MyPy                       |
| CI/CD       | GitHub/GitLab Actions      | GitHub/GitLab Actions            |
| Monitoring  | Sentry, Vercel            | Sentry, Prometheus, OpenTelemetry |
| Migrations  | —                          | Alembic                          |
| Task Queue  | —                          | ARQ / Celery                     |
| Secrets     | —                          | Vault / AWS Secrets Manager       |
| Audit Logs  | —                          | Append-only audit table           |
| Contracts   | Pact / jest-json-schema    | OpenAPI schema validation         |

---

## Code Quality Principles

### SOLID
- **S**ingle Responsibility - one function/class does one thing
- **O**pen-Closed - open for extension, closed for modification
- **L**iskov Substitution - subclasses must be substitutable
- **I**nterface Segregation - small, specific interfaces
- **D**ependency Inversion - depend on abstractions

### DRY (Don't Repeat Yourself)
- Extract common logic to shared utilities/hooks
- Server-driven config eliminates duplicate UI logic
- Centralize validation rules (backend is single source of truth)

### KISS (Keep It Simple Stupid)
- Simple > Clever
- Hard to explain = wrong approach

### YAGNI (You Aren't Gonna Need It)
- Don't build for tomorrow's requirements
- Solve today's problem first

### Naming Conventions

#### JavaScript / TypeScript
- `camelCase` - variables, functions
- `PascalCase` - classes, components, types
- `SCREAMING_SNAKE_CASE` - constants

#### Python
- `snake_case` - variables, functions, modules
- `PascalCase` - classes
- `UPPER_CASE` - module-level constants
- `_leading_underscore` - internal / private

**Both:** names should describe **what it does**, not how it does it

---

## Glossary

| Abbreviation | Full Name | Definition |
|--------------|-----------|------------|
| ABAC | Attribute-Based Access Control | Access control based on user, resource, and action attributes |
| ARQ | Asynchronous Request Queue | Redis-backed task queue for Python |
| CI/CD | Continuous Integration/Deployment | Automated build and deployment pipeline |
| CLS | Cumulative Layout Shift | Web Vital measuring visual stability |
| CSP | Content Security Policy | HTTP header preventing XSS attacks |
| CRUD | Create, Read, Update, Delete | Basic data operations |
| Eager Loading | — | Loading related data in the same query to avoid N+1 problems (opposite of lazy loading) |
| LCP | Largest Contentful Paint | Web Vital measuring loading performance |
| INP | Interaction to Next Paint | Web Vital measuring responsiveness |
| N+1 | N+1 Query Problem | Database query pattern causing performance issues |
| ORM | Object-Relational Mapping | Database abstraction layer |
| PII | Personally Identifiable Information | User data requiring protection |
| SDUI | Server-Driven UI | Pattern where backend controls UI structure via schema/config responses |
| selectinload | Select-In Loading | SQLAlchemy eager loading strategy that issues separate IN queries for related data |
| SSO | Single Sign-On | Authentication allowing one login for multiple services |

---

## Commit Format

```
<type>(<scope>): <description>

feat(auth): add JWT refresh token rotation
fix(api): handle connection pool exhaustion
docs(readme): update setup instructions
```

**Types:** `feat | fix | docs | style | refactor | perf | test | build | ci | chore | revert`

**Rules:**
- Subject ≤ 50 chars (soft guideline), max 72 chars (hard limit), lowercase, no period
- Body (optional): wrap at 72 chars, explain *why* not *what*
- **Never include AI agent attribution** in commits — commit history should reflect human decisions and ownership; attributing code to AI tools clutters blame annotations and obscures who reviewed and accepted the change

---

## AI/LLM Integration (If Applicable)

### Maker-Checker Pattern
- Separate generation from validation
- Self-healing loops - feed checker suggestions back to generator
- Confidence scores - have AI rate its own outputs

### Output Enforcement
- **Strict JSON** - command LLMs to return deterministic JSON
- **Schema validation** - Pydantic for structure
- **Retry logic** - with exponential backoff

### Cost Control
- **Rate limiting** on AI endpoints
- **Caching** generated content
- **Token tracking** - log usage
