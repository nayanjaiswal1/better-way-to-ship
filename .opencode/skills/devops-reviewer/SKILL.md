---
name: devops-reviewer
description: Review DevOps setup - CI/CD pipelines, Docker, Kubernetes, and infrastructure as code
license: MIT
compatibility: opencode
metadata:
  audience: devops-engineers
  scope: infrastructure
---

## When to Use

Use this skill when reviewing DevOps/infra code. Load with: `skill({ name: "devops-reviewer" })`

## Review Checklist

### Docker (see `best-practices/devops.md`)
- Multi-stage builds for smaller images
- No root user
- Proper .dockerignore
- Health checks defined
- Layer caching optimized

### CI/CD (see `best-practices/devops.md`)
- Fast feedback loops
- Proper caching (deps, artifacts)
- Secret management (no hardcoded secrets)
- Parallel jobs when possible
- Post-mortems on failures

### Kubernetes (see `best-practices/kubernetes.md`)
- Resource limits set
- Liveness/readiness probes
- HPA configured
- PodDisruptionBudget for critical apps
- Proper namespace isolation

### Security (see `best-practices/security-hardening.md`)
- No privileged containers
- Read-only root filesystems
- Network policies
- Secrets mounted, not env vars
- Image scanning in CI

### Observability (see `best-practices/observability.md`)
- Structured logging
- Metrics exported
- Tracing configured
- Dashboards for key metrics
- Alerts with runbooks

### Disaster Recovery (see `best-practices/disaster-recovery.md`)
- Backup strategy documented
- RTO/RPO defined
- Failover tested
- Runbooks exist

### Cost Optimization (see `best-practices/cost-optimization.md`)
- Spot instances where appropriate
- Reserved instances for steady state
- Auto-scaling configured
- Unused resources cleaned up

## Pipeline Checklist

### ✅ Required
- [ ] Lint/format checks
- [ ] Unit tests
- [ ] Integration tests
- [ ] Security scans (SAST)
- [ ] Build Docker image
- [ ] Push to registry
- [ ] Deploy to environment
- [ ] Smoke tests

### ⚠️ Security
- [ ] No secrets in logs
- [ ] Dependencies scanned
- [ ] Container image signed

## Example Output

```
## DevOps Best Practices Review

### ✅ Passed
- Multi-stage Docker build
- Resource limits set

### ⚠️ Issues
- **Security**: Container running as root
  Fix: Add USER directive in Dockerfile
  See: best-practices/devops.md#docker

- **Missing**: No readiness probe
  Fix: Add probe configuration
  See: best-practices/kubernetes.md#probes

### ❌ Critical
- **Secret**: API key hardcoded in CI
  Fix: Use secrets manager
  See: best-practices/security-hardening.md#secrets
```
