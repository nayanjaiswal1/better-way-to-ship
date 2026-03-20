# Security Hardening

## TLS Configuration

### Nginx / Traefik — strong TLS only

```nginx
# nginx/conf.d/ssl.conf
server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate     /etc/ssl/certs/api.crt;
    ssl_certificate_key /etc/ssl/private/api.key;

    # Protocols — TLS 1.2+ only
    ssl_protocols TLSv1.2 TLSv1.3;

    # Strong ciphers only — no RC4, DES, MD5
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;

    # HSTS — force HTTPS for 1 year, include subdomains
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # OCSP Stapling — faster certificate validation
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Redirect all HTTP to HTTPS
    if ($scheme != "https") {
        return 301 https://$host$request_uri;
    }
}
```

### Verify TLS config

```bash
# Test with SSL Labs (external)
curl "https://api.ssllabs.com/api/v3/analyze?host=api.example.com"
# Target: A+ rating

# Test locally
nmap --script ssl-enum-ciphers -p 443 api.example.com
openssl s_client -connect api.example.com:443 -tls1    # ✅ should fail
openssl s_client -connect api.example.com:443 -tls1_2  # ✅ should succeed
```

---

## Security Headers — Complete

```python
# middleware/security_headers.py
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)

    response.headers.update({
        # Prevent clickjacking
        "X-Frame-Options": "DENY",

        # Prevent MIME type sniffing
        "X-Content-Type-Options": "nosniff",

        # Force HTTPS for 1 year
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",

        # Control referrer info
        "Referrer-Policy": "strict-origin-when-cross-origin",

        # Disable browser features not needed
        "Permissions-Policy": (
            "accelerometer=(), camera=(), geolocation=(), "
            "gyroscope=(), magnetometer=(), microphone=(), "
            "payment=(), usb=()"
        ),

        # XSS protection (legacy browsers)
        "X-XSS-Protection": "1; mode=block",

        # Don't expose server info
        "Server": "server",   # override uvicorn default

        # Content Security Policy
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'nonce-{nonce}'; "       # use nonces for inline scripts
            "style-src 'self' 'unsafe-inline'; "         # allow inline styles (Tailwind)
            "img-src 'self' data: https://cdn.example.com; "
            "font-src 'self'; "
            "connect-src 'self' https://api.example.com wss://api.example.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        ),

        # Cross-Origin policies
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cross-Origin-Embedder-Policy": "require-corp",
    })

    return response
```

### Verify headers

```bash
curl -I https://app.example.com | grep -E "(Content-Security|X-Frame|X-Content|Strict-Transport|Referrer|Permissions)"

# Use securityheaders.com for full analysis
# Target: A+ rating
```

---

## Dependency Scanning in CI

```yaml
# .github/workflows/security.yml
name: Security Scan

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 6 * * 1'  # weekly Monday 6am

jobs:
  python-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pip-audit
      - run: pip-audit -r requirements.txt --output json > pip-audit-results.json
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: pip-audit-results
          path: pip-audit-results.json

  node-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci --prefix frontend
      - run: npm audit --audit-level=high --prefix frontend

  container-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -t myapp:${{ github.sha }} .
      - name: Scan with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: myapp:${{ github.sha }}
          format: sarif
          output: trivy-results.sarif
          severity: CRITICAL,HIGH
          exit-code: 1   # fail CI on critical/high CVEs

  sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Semgrep SAST
        uses: semgrep/semgrep-action@v1
        with:
          config: >-
            p/python
            p/fastapi
            p/react
            p/jwt
            p/secrets
```

---

## SAST — Static Analysis Security Testing

```bash
# Semgrep — finds security issues in code
pip install semgrep

# Scan Python
semgrep --config p/python --config p/fastapi app/

# Scan JavaScript/TypeScript
semgrep --config p/react --config p/javascript frontend/src/

# Custom rules for your patterns
semgrep --config custom-rules.yaml .
```

```yaml
# custom-rules.yaml — catch common mistakes
rules:
  - id: no-raw-sql
    patterns:
      - pattern: session.execute("..." % ...)
      - pattern: session.execute(f"...")
    message: "Raw SQL with string formatting — use parameterized queries"
    severity: ERROR
    languages: [python]

  - id: no-debug-in-prod
    pattern: app = FastAPI(debug=True)
    message: "Debug mode enabled — remove for production"
    severity: WARNING
    languages: [python]

  - id: no-localstorage-token
    patterns:
      - pattern: localStorage.setItem('token', ...)
      - pattern: localStorage.setItem('access_token', ...)
    message: "Never store tokens in localStorage — use httpOnly cookies"
    severity: ERROR
    languages: [javascript, typescript]
```

---

## Secrets Rotation — Zero Downtime

### Rotate DB password without downtime

```bash
# 1. Add new password to Secrets Manager (keep old active)
aws secretsmanager put-secret-value \
  --secret-id prod/db-password \
  --secret-string '{"password":"new_password","old_password":"old_password"}'

# 2. Update app to try new password, fall back to old (deploy)
# 3. Wait for all old connections to drain
# 4. Remove old password from Secrets Manager
# 5. Change DB password
```

```python
# core/db.py — support dual passwords during rotation
async def get_engine():
    secret = await get_secret("prod/db-password")
    try:
        engine = create_async_engine(build_url(secret["password"]))
        await engine.connect()
        return engine
    except Exception:
        # Fallback to old password during rotation
        if "old_password" in secret:
            return create_async_engine(build_url(secret["old_password"]))
        raise
```

### Rotate JWT secret key

```python
# Support multiple signing keys during rotation
class JWTKeyManager:
    def __init__(self, keys: list[str]):
        self.keys = keys  # first = current signing key, rest = accepted for verification

    def create_token(self, data: dict) -> str:
        return jwt.encode(data, self.keys[0], algorithm="HS256")

    def verify_token(self, token: str) -> dict:
        for key in self.keys:
            try:
                return jwt.decode(token, key, algorithms=["HS256"])
            except JWTError:
                continue
        raise JWTError("Token verification failed")

# Rotation: add new key as first, keep old as second
# After old tokens expire (15 min) — remove old key
key_manager = JWTKeyManager(keys=[
    settings.JWT_SECRET_KEY_NEW,
    settings.JWT_SECRET_KEY_OLD,
])
```

---

## Input Validation Hardening

```python
# core/validators.py — reusable validators
from pydantic import field_validator
import re

def validate_no_html(value: str) -> str:
    """Reject HTML tags in plain text fields."""
    if re.search(r'<[^>]+>', value):
        raise ValueError("HTML not allowed in this field")
    return value

def validate_safe_filename(value: str) -> str:
    """Prevent path traversal in filenames."""
    if '..' in value or '/' in value or '\\' in value:
        raise ValueError("Invalid filename")
    return value

def validate_url_allowlist(value: str, allowed_domains: list[str]) -> str:
    """Only allow URLs from specific domains."""
    from urllib.parse import urlparse
    parsed = urlparse(value)
    if parsed.hostname not in allowed_domains:
        raise ValueError(f"URL must be from: {', '.join(allowed_domains)}")
    return value

# Usage in schemas
class PostCreate(BaseModel):
    title: str
    body: str

    @field_validator('title')
    @classmethod
    def title_no_html(cls, v): return validate_no_html(v)

class FileUpload(BaseModel):
    filename: str

    @field_validator('filename')
    @classmethod
    def safe_filename(cls, v): return validate_safe_filename(v)
```

---

## Security Monitoring

```python
# Track security events — feed into alerting
async def log_security_event(event_type: str, request: Request, **context):
    log = structlog.get_logger()
    log.warning(
        "security_event",
        event_type=event_type,
        ip=request.client.host,
        user_agent=request.headers.get("user-agent"),
        path=str(request.url),
        **context,
    )
    # Also push to SIEM/security dashboard

# Use in auth endpoints
async def login(...):
    try:
        user = await service.authenticate_user(data.email, data.password)
    except NotFoundError:
        await log_security_event("failed_login", request, email=data.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    await log_security_event("successful_login", request, user_id=user.public_id)
```

### Alert on security events

```yaml
# Prometheus alert — spike in failed logins = brute force
- alert: BruteForceDetected
  expr: rate(security_events_total{event_type="failed_login"}[5m]) > 10
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Possible brute force attack — {{ $value }} failed logins/sec"

- alert: UnauthorizedAccessSpike
  expr: rate(http_requests_total{status="403"}[5m]) > 20
  for: 3m
  labels:
    severity: warning
  annotations:
    summary: "Spike in 403 responses — possible probing"
```

---

## Security Hardening Checklist

### Transport
- [ ] TLS 1.2+ only — no SSLv3, TLSv1.0, TLSv1.1
- [ ] Strong cipher suites only
- [ ] HSTS with `preload` directive
- [ ] OCSP stapling enabled
- [ ] SSL Labs score: A+

### Headers
- [ ] CSP header with strict directives
- [ ] X-Frame-Options: DENY
- [ ] X-Content-Type-Options: nosniff
- [ ] Referrer-Policy set
- [ ] Permissions-Policy disables unused features
- [ ] Server header obscured

### Dependencies
- [ ] `pip-audit` in CI — fail on HIGH/CRITICAL
- [ ] `npm audit` in CI
- [ ] Container scanned with Trivy
- [ ] Dependabot auto-PRs enabled
- [ ] SAST (Semgrep) in CI

### Secrets
- [ ] All secrets in Secrets Manager — not env vars
- [ ] Secret rotation procedure documented and tested
- [ ] JWT key rotation supported (dual-key verification)
- [ ] No secrets in git history (`git log -S "password"`)
- [ ] No secrets in Docker images (`docker history myapp`)

### Runtime
- [ ] Security events logged with IP + user agent
- [ ] Alerts on brute force + 403 spikes
- [ ] Failed login attempts trigger lockout after threshold
- [ ] Rate limiting on all public endpoints
