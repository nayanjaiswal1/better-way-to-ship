---
name: security-auditor
description: Security audit for any codebase - OWASP Top 10, common vulnerabilities, and hardening
license: MIT
compatibility: opencode
metadata:
  audience: security-conscious
  scope: all-frameworks
---

## When to Use

Use this skill when performing security reviews. Load with: `skill({ name: "security-auditor" })`

## OWASP Top 10 Checklist (see `best-practices/pentesting.md`)

### A01 - Broken Access Control
- No IDOR (Insecure Direct Object References)
- Proper authorization on all endpoints
- Admin routes protected
- See: `best-practices/permissions.md`, `best-practices/security.md`

### A02 - Cryptographic Failures
- Passwords hashed with bcrypt/argon2
- Sensitive data not in logs
- HTTPS everywhere
- See: `best-practices/security.md`, `best-practices/security-hardening.md`

### A03 - Injection
- Parameterized queries only
- Input sanitization
- No eval() or exec()
- See: `best-practices/security.md`

### A04 - Insecure Design
- Business logic flaws
- Rate limiting
- Proper error messages
- See: `best-practices/resilience.md`

### A05 - Security Misconfiguration
- CORS properly configured
- Debug mode off in production
- Security headers set
- See: `best-practices/security-hardening.md`

### A06 - Vulnerable Components
- Dependencies up to date
- No known CVEs
- See: `best-practices/security-hardening.md#dependencies`

### A07 - Auth Failures
- Strong password policies
- Session management secure
- 2FA available
- See: `best-practices/auth-advanced.md`

### A08 - Data Integrity Failures
- CSRF protection
- File upload validation
- See: `best-practices/security.md`

### A09 - Logging & Monitoring
- Failed logins logged
- Errors don't leak info
- See: `best-practices/observability.md`, `best-practices/audit-logging.md`

### A10 - SSRF
- URL validation for external requests
- Allowlists for APIs
- See: `best-practices/pentesting.md`

## Security Headers (see `best-practices/security-hardening.md`)

```
Content-Security-Policy
X-Frame-Options
Strict-Transport-Security
X-Content-Type-Options
Referrer-Policy
```

## How to Audit

1. Run: `npx nuclei -t nuclei-templates/http/vulnerabilities/ -l https://target.com`
2. Check for OWASP Top 10 issues
3. Review code for IDOR, SQLi, XSS
4. Verify security headers
5. Check dependency vulnerabilities

## Output Format

```
## Security Audit

### Critical
- [ ] SQL Injection in /api/users - use parameterized queries
- [ ] IDOR in /api/posts/{id}/delete - check ownership

### High
- [ ] No rate limiting on /api/login
- [ ] Missing CSRF token

### Medium
- [ ] Debug mode enabled
- [ ] Missing security headers
```
