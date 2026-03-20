# Production-Ready Best Practices: React & FastAPI

**Audience**: Intermediate to advanced developers familiar with TypeScript, Python, and web development fundamentals.

---

## Files

### Backend

| File | Contents |
|------|----------|
| [fastapi.md](./fastapi.md) | Project Structure, Architecture, Repository Pattern, Performance, API Design, Error Handling, Checklist |
| [django.md](./django.md) | Project Structure, DRF ViewSets, Serializers, Auth (JWT Cookies), Middleware, ORM Patterns, Admin, Checklist |
| [django-celery.md](./django-celery.md) | Celery Setup, Task Queues, Scheduled Tasks (Beat), Chaining, Idempotency, KEDA Scaling, Flower |
| [django-testing.md](./django-testing.md) | pytest-django, Factory Boy, API Client Fixtures, View/Auth/Service/Task Tests, Coverage |
| [django-multitenancy.md](./django-multitenancy.md) | TenantScopedManager, Tenant Middleware, RLS, Tenant-Aware Cache, Celery Task Context |
| [django-permissions.md](./django-permissions.md) | Role Hierarchy, DRF Permission Classes, ABAC PermissionChecker, Field-Level, Bootstrap Permissions |
| [django-events.md](./django-events.md) | Django Signals, on_commit, Celery Side Effects, Notifications, SSE Delivery, Outbound Webhooks |
| [django-realtime.md](./django-realtime.md) | SSE via StreamingResponse, Django Channels WebSocket, JWT Auth Middleware, Celery Push, Nginx Config |
| [django-resilience.md](./django-resilience.md) | DRF Throttling, Custom Throttle Classes, Tenant Rate Limits, Circuit Breaker, Timeouts, Graceful Degradation |

### Frontend

| File | Contents |
|------|----------|
| [react.md](./react.md) | Architecture, State, Performance, Data Fetching, Forms, Error Handling, Checklist |
| [frontend-advanced.md](./frontend-advanced.md) | i18n, Image Optimization, File Uploads (S3), Multi-Step Forms, Input Sanitization |
| [frontend-patterns.md](./frontend-patterns.md) | Dark Mode/Theming, Headless Components, Compound Components, Analytics (PostHog) |
| [typescript-advanced.md](./typescript-advanced.md) | Utility Types, Discriminated Unions, Generic Components, Template Literals, a11y Testing |
| [storybook.md](./storybook.md) | Component Documentation, Stories, MSW Integration, Play Functions, Chromatic Visual Regression, A11y |
| [feature-flags.md](./feature-flags.md) | Feature Flags, Flag Lifecycle, React Integration |

### Shared / Full-Stack

| File | Contents |
|------|----------|
| [security.md](./security.md) | Security Checklist, Auth & Token Management, Secrets Management |
| [testing.md](./testing.md) | React (Vitest + RTL), FastAPI (pytest + pytest-asyncio) |
| [observability.md](./observability.md) | Logging, Tracing, Metrics, Alerting Thresholds, Audit Logging, Dependency Security, Common Mistakes |
| [api-patterns.md](./api-patterns.md) | Bootstrap, Schema/Data Split, ETags, Field Selection, Idempotency Keys, Prefetching, Infinite Scroll |
| [openapi-contracts.md](./openapi-contracts.md) | TypeScript Type Generation, openapi-fetch, Contract Testing (Schemathesis), Breaking Change Detection |
| [realtime.md](./realtime.md) | Polling, SSE (Server-Sent Events), WebSocket, Decision Guide |
| [resilience.md](./resilience.md) | Exponential Backoff, Circuit Breaker, Timeouts, Graceful Degradation, Rate Limiting |
| [auth-advanced.md](./auth-advanced.md) | OAuth/SSO (Google, GitHub), 2FA/MFA (TOTP, Backup Codes) |
| [permissions.md](./permissions.md) | RBAC, ABAC, Permission Checker, Field-Level Permissions, React Integration |
| [events.md](./events.md) | Domain Events, Event Bus, Email/Notifications, Notification Preferences |
| [payments.md](./payments.md) | Stripe Checkout, Subscriptions, Webhooks, Billing Portal, Plan Gating |
| [integrations.md](./integrations.md) | Outbound Webhooks, Sentry Error Tracking |
| [ai-llm.md](./ai-llm.md) | Streaming Responses, RAG (pgvector), Multi-Turn Conversations, Tool Use, Cost Tracking, Prompt Management |
| [search.md](./search.md) | Elasticsearch/OpenSearch Setup, Index Mapping, Celery Indexing, Full-Text + Faceted Search, Autocomplete |
| [email-deliverability.md](./email-deliverability.md) | SPF/DKIM/DMARC, Bounce Handling, Spam Complaints, Unsubscribe (RFC 8058), Templates, Mailpit |
| [audit-logging.md](./audit-logging.md) | Immutable Audit Log Model, Diff Tracking, Auth Middleware, DB Tamper Prevention, Archival, SOC2/GDPR |

### Infrastructure & Data

| File | Contents |
|------|----------|
| [infrastructure.md](./infrastructure.md) | ID Strategy (BIGINT + ULID + NanoID), Background Jobs, DB Migrations, Caching, Read Replicas, PgBouncer, API Versioning, Optimistic Locking, Soft Deletes, Type Sharing |
| [database.md](./database.md) | Indexing Strategy, EXPLAIN ANALYZE, Slow Query Logging, Full-Text Search |
| [multitenancy.md](./multitenancy.md) | Tenant Isolation, Row-Level Security, Tenant Middleware, Tenant-Aware Caching (FastAPI) |
| [django-multitenancy.md](./django-multitenancy.md) | TenantScopedManager, Tenant Middleware, RLS, Tenant-Aware Cache, Celery Task Context (Django) |
| [zero-downtime-migrations.md](./zero-downtime-migrations.md) | Expand-Contract Pattern, Safe Column Add/Rename/Drop, Large Backfills, CONCURRENTLY Indexes |
| [data.md](./data.md) | CSV/Excel Export, DB Transactions, Data Factories, Cron Jobs, Materialized Views |

### Security

| File | Contents |
|------|----------|
| [pentesting.md](./pentesting.md) | OWASP Top 10 Tests, IDOR, Brute Force, XSS, SQLi, SSRF, Tools (ZAP, sqlmap, nuclei), Checklist |
| [security-hardening.md](./security-hardening.md) | TLS Config, Security Headers, Dependency Scanning CI, SAST (Semgrep), Secrets Rotation, Security Monitoring |
| [gdpr.md](./gdpr.md) | Data Export, Right to Erasure, Cookie Consent, Data Retention |

### Operations

| File | Contents |
|------|----------|
| [kubernetes.md](./kubernetes.md) | Deployment, HPA, PDB, Probes, KEDA (Event-Driven Autoscaling), Terraform IaC |
| [devops.md](./devops.md) | Docker, CI/CD, Environment Parity, Load Testing (k6), Blue-Green Deployments |
| [dx.md](./dx.md) | Git Hooks, Makefile, Local Dev Setup, DB Backup Strategy, CORS, CSP |
| [performance-profiling.md](./performance-profiling.md) | py-spy, Memory Leak Prevention, React Profiler, Bundle Budget |
| [cdn.md](./cdn.md) | CloudFront Setup, Cache Headers, S3 Deploy, Image CDN (imgproxy), Cache Invalidation, Bundle Budget CI |
| [file-processing.md](./file-processing.md) | PDF Generation (WeasyPrint), Image Resizing (Pillow), Virus Scanning (ClamAV), Magic Byte Validation, Excel |
| [slo.md](./slo.md) | SLIs/SLOs/Error Budgets, Burn Rate Alerts, Error Budget Policy, Business SLOs, Grafana Dashboard |
| [disaster-recovery.md](./disaster-recovery.md) | RTO/RPO Targets, PITR, Cross-Region Failover, S3 Replication, DR Runbook, DR Testing |
| [cost-optimization.md](./cost-optimization.md) | Spot Instances, RDS Reserved, S3 Lifecycle, PgBouncer, Right-Sizing, Budget Alerts |

### General

| File | Contents |
|------|----------|
| [microservices.md](./microservices.md) | Service Decomposition, HTTP + Async Messaging, Service Discovery, API Gateway, Service Auth, Saga Pattern |
| [sharding.md](./sharding.md) | Table Partitioning, Tenant-Based Sharding, Consistent Hashing, Shard Router (Django/FastAPI), Cross-Shard Queries, Resharding |
| [webrtc.md](./webrtc.md) | Signaling Server (Django Channels + FastAPI), STUN/TURN (coturn), React useWebRTC Hook, Data Channels, Video Call UI |
| [principles.md](./principles.md) | Shared Practices, SOLID/DRY/KISS/YAGNI, Naming Conventions, Glossary, Commit Format, AI/LLM |
| [project-structure.md](./project-structure.md) | React Feature-Based Structure, FastAPI Layered Structure |
| [monorepo.md](./monorepo.md) | Turborepo, pnpm Workspaces, Shared UI/Types/Config Packages, Remote Cache, CI Affected-Only Builds |
| [backend-i18n.md](./backend-i18n.md) | Django gettext, FastAPI Babel, Locale Middleware, User Preference, Localized Emails |
| [admin-panel.md](./admin-panel.md) | Django Admin (Enhanced), react-admin, Admin API Endpoints, Impersonation, Audit All Admin Actions |
