# Observability

## The Three Pillars

### 1. Structured Logging
- Use structlog (already recommended)
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Include: correlation_id, user_id, request_id, tenant_id
- Never log sensitive data (passwords, tokens, PII)

```python
# core/logging.py
import logging
import structlog
from structlog.processors import JSONRenderer

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

# Usage in services/routers
log = structlog.get_logger()

log.info("user_action", user_id=123, action="login")  # Avoid logging IP addresses (PII under GDPR)
log.error("request_failed", request_id="abc", error="timeout")
```

### 2. Distributed Tracing (OpenTelemetry)
- Trace requests across services
- Understand latency bottlenecks
- Correlate logs with traces
- Use W3C Trace Context

### 3. Metrics (Prometheus)
- Request rate
- Error rate
- Latency histograms
- Business metrics (user signups, orders, etc.)

## Tools
- **Tracing**: Jaeger, Tempo, Zipkin
- **Metrics**: Prometheus + Grafana
- **Logs**: ELK Stack, Loki
- **Alerting**: PagerDuty, OpsGenie

---

## Alerting Thresholds

Define what wakes someone up — too many alerts = alert fatigue, too few = missed incidents.

### Error Rate
```
< 0.1%   → OK
0.1–1%   → Warning (Slack notification)
> 1%     → Critical (PagerDuty — wake someone up)
> 5%     → Incident (all hands)
```

### Latency (p95)
```
< 200ms  → OK
200–500ms → Warning
> 500ms  → Critical (API SLA breach)
> 2s     → Incident
```

### Infrastructure
```
CPU      > 80% for 5min   → Warning | > 90% for 2min → Critical
Memory   > 85%            → Warning | > 95%          → Critical
Disk     > 80%            → Warning | > 90%          → Critical (fill fast)
DB conns > 80% of max     → Warning | > 95%          → Critical
```

### Business Metrics (Silent Failures)
```
# These don't throw errors — they just silently stop working
Signups last 1h    < 50% of hourly average → Warning
Orders last 1h     = 0                     → Critical (payment broken?)
Emails sent last 1h = 0                    → Warning (email provider down?)
Background jobs queue > 1000 pending       → Warning
```

### Prometheus Rules Example

```yaml
# alerts.yml
groups:
  - name: api
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Error rate above 1%"

      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "p95 latency above 500ms"

      - alert: DatabaseConnectionsHigh
        expr: pg_stat_activity_count / pg_settings_max_connections > 0.8
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "DB connections above 80%"
```

---

## Audit Logging

### What to Audit
- User login/logout
- Permission changes
- Resource deletion
- Data export
- Admin actions
- Failed authentication attempts

### Implementation
- Immutable audit log table (append-only)
- Include: who, what, when, where (IP), result
- Never delete audit logs
- Consider streaming to separate audit system

---

## Dependency Security

### Supply Chain Attacks Are Real
- **PyPI**: pip-audit, safety
- **npm**: npm audit, Snyk, Dependabot
- **GitHub**: Dependabot, Renovate for auto-updates

### Practices
- Pin exact versions in production (no `latest`)
- Review changelogs before updating
- Use lock files (pip-tools `requirements.txt`, uv `uv.lock`, `package-lock.json`)
- Scan dependencies in CI/CD pipeline
- Remove unused dependencies regularly

---

## Contract Testing

### The Problem
Server-driven UI depends on exact API response shape. Breaking changes don't fail tests until production.

### Solution: Pact or Schema Snapshots
- **Pact**: consumer-driven contracts
- **jest-json-schema**: validate responses against schema
- **ajv**: validate API responses at runtime in tests

### Pattern
- Frontend defines expected API shape
- Backend implements to contract
- CI verifies both sides match

---

## Common Mistakes & How to Avoid Them

### React Mistakes
| Mistake | Why It's a Problem | Correct Approach |
|---------|-------------------|------------------|
| Storing JWT in localStorage | XSS can steal tokens | Use httpOnly cookies |
| Ignoring error boundaries | Uncaught errors crash the app | Wrap components in ErrorBoundary |
| Overusing useState | Causes unnecessary re-renders | Use derived state, URL state, or server state |
| Anonymous functions in render | New object reference each render | Define functions outside or use useCallback |
| Not canceling API requests | Memory leaks, race conditions | Use AbortController or React Query |

### FastAPI Mistakes
| Mistake | Why It's a Problem | Correct Approach |
|---------|-------------------|------------------|
| Using BackgroundTasks in production | Dies with worker, no retry | Use ARQ or Celery |
| Sync database operations | Blocks async event loop | Use async SQLAlchemy with asyncpg |
| Not using connection pooling | Exhausts DB connections under load | Use PgBouncer |
| Returning HTTPException from services | Couples business logic to HTTP | Use custom AppError, handle in exception handler |
| Missing database indexes | Slow queries at scale | Add indexes on frequently queried columns |

### Database Mistakes
| Mistake | Why It's a Problem | Correct Approach |
|---------|-------------------|------------------|
| Using OFFSET for pagination | Performance degrades with large offsets | Use cursor-based pagination |
| N+1 queries | Too many database round trips | Use eager loading (selectinload) |
| Not using transactions | Inconsistent data state | Wrap related operations in transactions |
| Modifying applied migrations | Breaks migration history | Create new migration instead |
