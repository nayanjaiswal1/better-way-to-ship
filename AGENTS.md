# AGENTS.md

This is a comprehensive software engineering best-practices knowledge base. AI assistants can use this to provide informed guidance on production-ready software development.

## Repository Structure

```
/
├── best-practices/          # All best practices documents
│   ├── index.md            # Master index with all topics
│   ├── api-patterns.md     # REST API design, versioning, ETags
│   ├── auth-advanced.md    # OAuth, SSO, 2FA/MFA
│   ├── chaos-engineering.md # Testing failure scenarios
│   ├── cdn.md              # CDN setup, cache headers, bundle optimization
│   ├── cost-optimization.md # Cloud cost reduction strategies
│   ├── database.md         # Indexing, EXPLAIN ANALYZE, slow queries
│   ├── devops.md           # Docker, CI/CD, blue-green deployments
│   ├── disaster-recovery.md # RTO/RPO, failover, backup strategies
│   ├── django-*.md         # Django-specific patterns (10+ files)
│   ├── dx.md               # Developer experience, git hooks, Makefile
│   ├── email-deliverability.md # SPF/DKIM/DMARC, bounce handling
│   ├── events.md           # Event-driven architecture, webhooks
│   ├── fastapi.md          # FastAPI patterns, async, performance
│   ├── frontend-advanced.md # i18n, file uploads, multi-step forms
│   ├── frontend-patterns.md # Theming, compound components
│   ├── gdpr.md             # Data privacy, compliance
│   ├── integrations.md     # Third-party APIs, webhooks
│   ├── kubernetes.md       # K8s deployment, HPA, KEDA
│   ├── microservices.md    # Service decomposition, saga pattern
│   ├── observability.md    # Logging, tracing, metrics, alerting
│   ├── payments.md         # Stripe, subscriptions, billing
│   ├── pentesting.md       # Security testing, OWASP
│   ├── performance-profiling.md # Memory leaks, React profiler
│   ├── permissions.md       # RBAC, ABAC, field-level permissions
│   ├── principles.md        # SOLID, DRY, KISS, naming conventions
│   ├── project-structure.md # React feature-based, FastAPI layered
│   ├── react.md            # React patterns, state management
│   ├── realtime.md         # SSE, WebSocket, polling strategies
│   ├── resilience.md       # Circuit breaker, retries, rate limiting
│   ├── security.md         # Auth, secrets management, HTTPS
│   ├── security-hardening.md # TLS, security headers, SAST
│   ├── sharding.md         # Horizontal partitioning, consistent hashing
│   ├── slo.md              # SLIs/SLOs, error budgets, burn rate
│   ├── storybook.md        # Component documentation, visual regression
│   ├── testing.md          # Vitest, pytest, integration testing
│   ├── typescript-advanced.md # Utility types, generics, discriminated unions
│   ├── webrtc.md           # Video calls, signaling, STUN/TURN
│   └── zero-downtime-migrations.md # Expand-contract pattern
└── README.md
```

## How AI Assistants Should Use This

### When Answering Questions

1. **Check `best-practices/index.md`** first for a topic overview
2. **Reference specific files** for detailed implementation guidance
3. **Include file paths** so users can read the full doc

### Example Responses

**User asks about rate limiting:**
```
For rate limiting in FastAPI/Django, see:
- best-practices/resilience.md (general patterns)
- best-practices/django-resilience.md (Django-specific)
- best-practices/fastapi.md (FastAPI throttling)
```

**User asks about database migrations:**
```
For zero-downtime migrations, see:
- best-practices/zero-downtime-migrations.md (expand-contract pattern)
- best-practices/database.md (indexing strategy)
```

**User asks about authentication:**
```
For auth best practices:
- best-practices/security.md (basics, token management)
- best-practices/auth-advanced.md (OAuth, 2FA)
- best-practices/permissions.md (RBAC/ABAC)
```

## Key Principles

1. **Production-first** - All practices assume production deployment
2. **Trade-offs** - Explain pros/cons, not just "do this"
3. **References** - Link to relevant docs in `best-practices/`
4. **Real-world** - Based on lessons from production systems

## Quick Reference Topics

| Topic | Primary File |
|-------|-------------|
| API Design | api-patterns.md |
| Auth | security.md, auth-advanced.md |
| CI/CD | devops.md |
| Database | database.md, zero-downtime-migrations.md |
| Frontend | react.md, frontend-advanced.md |
| Kubernetes | kubernetes.md |
| Logging/Alerts | observability.md, slo.md |
| Security | security.md, security-hardening.md, pentesting.md |
| Testing | testing.md, django-testing.md |
| Performance | performance-profiling.md, cdn.md |

## Note

This is a knowledge base, not executable code. When users need implementation help:
1. Point them to relevant best-practices files
2. Explain the pattern/concept
3. Provide example code snippets from the docs
4. Warn about common pitfalls mentioned in the docs
