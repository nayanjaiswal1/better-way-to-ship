# DevOps

## Docker Best Practices

### Image Optimization
- Multi-stage builds for smaller final images
- Combine RUN commands and cleanup in same layer
- Use `PYTHONUNBUFFERED=1` for real-time logs
- Use `PYTHONDONTWRITEBYTECODE=1` for cleaner images

```dockerfile
# FastAPI multi-stage Dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose
- **Healthchecks** - `pg_isready` for postgres
- `depends_on condition: service_healthy`
- **Named volumes** - prevent data loss

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/mydb
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3

  db:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=mydb
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d mydb"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

---

## CI/CD Pipeline

### Stages
1. **Lint/Type Check** - fast, catch basics
2. **Test** - unit + integration
3. **Build** - compile/build image
4. **Deploy** - to environment

### Optimization
- Pre-baked images with dependencies pre-installed
- Content-hash tagging - rebuild only on code change
- Cache `.ruff_cache`, `.mypy_cache`, `UV_CACHE_DIR`
- Interruptible pipelines - kill stale builds

---

## Environment Parity

### The Goal: Production Works on My Machine
- Same Docker images across all environments
- Same environment variables (different values)
- Same database schema
- Same Redis cache structure

### The 12-Factor App Principles
- Config from environment (not code)
- Stateless processes
- Disposability (graceful shutdown)

### Dev Environment
- Use Docker Compose for all services
- Seed with realistic test data
- Use same images as production

---

## Load Testing

Run before every major release — know your limits before users find them.

```bash
# brew install k6
```

```javascript
// k6/load-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '1m', target: 50 },   // ramp up to 50 users
    { duration: '3m', target: 50 },   // hold at 50 users
    { duration: '1m', target: 100 },  // ramp up to 100 users
    { duration: '3m', target: 100 },  // hold at 100 users
    { duration: '1m', target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% of requests under 500ms
    errors: ['rate<0.01'],             // error rate under 1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

// Reuse auth token across iterations
export function setup() {
  const res = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: 'load@test.com',
    password: 'testpassword',
  }), { headers: { 'Content-Type': 'application/json' } });
  return { token: res.cookies.access_token[0].value };
}

export default function (data) {
  const headers = {
    'Content-Type': 'application/json',
    Cookie: `access_token=${data.token}`,
  };

  // Test critical paths
  const responses = http.batch([
    ['GET', `${BASE_URL}/api/v1/users`, null, { headers }],
    ['GET', `${BASE_URL}/api/v1/users/schema`, null, { headers }],
    ['GET', `${BASE_URL}/api/v1/bootstrap`, null, { headers }],
  ]);

  responses.forEach(res => {
    check(res, { 'status is 200': r => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  sleep(1);
}
```

```bash
# Run load test
k6 run --env BASE_URL=https://staging.example.com k6/load-test.js

# Run in CI before deploy to production
k6 run --exit-on-running-error k6/load-test.js
```

---

## Blue-Green Deployment

Zero downtime deploys — switch traffic between two identical environments.

```
Blue (current live) → Green (new version)
                    → run health checks on Green
                    → switch load balancer to Green
                    → Blue becomes standby
                    → rollback = switch back to Blue instantly
```

```yaml
# docker-compose.prod.yml — two identical app services
services:
  api-blue:
    image: myapp:${BLUE_VERSION}
    labels:
      - "traefik.http.routers.api.rule=Host(`api.example.com`)"
      - "traefik.http.services.api.loadbalancer.server.port=8000"

  api-green:
    image: myapp:${GREEN_VERSION}
    labels:
      - "traefik.http.routers.api-green.rule=Host(`api.example.com`) && Headers(`X-Canary`, `true`)"
```

```bash
#!/bin/bash
# scripts/deploy.sh

NEW_VERSION=$1
CURRENT=$(docker inspect --format='{{.Config.Image}}' api-blue | cut -d: -f2)

echo "Deploying $NEW_VERSION (current: $CURRENT)"

# 1. Deploy to green
GREEN_VERSION=$NEW_VERSION docker compose up -d api-green

# 2. Run migrations (backward compatible only)
docker compose exec api-green alembic upgrade head

# 3. Health check green
for i in {1..30}; do
  STATUS=$(curl -sf http://localhost:8001/health | jq -r .status)
  if [ "$STATUS" = "ok" ]; then
    echo "Green is healthy"
    break
  fi
  sleep 2
done

if [ "$STATUS" != "ok" ]; then
  echo "Green failed health check — aborting"
  docker compose stop api-green
  exit 1
fi

# 4. Switch traffic (update Traefik/nginx config)
export ACTIVE=green
docker compose up -d traefik

# 5. Old blue becomes standby
BLUE_VERSION=$CURRENT docker compose up -d api-blue

echo "Deploy complete. Rollback: ./scripts/rollback.sh"
```

```bash
# scripts/rollback.sh — instant rollback
export ACTIVE=blue
docker compose up -d traefik
echo "Rolled back to blue"
```

---

## Environment Variables

### FastAPI
```
APP_NAME, APP_VERSION, DEBUG, SECRET_KEY
DATABASE_URL, REDIS_URL
ALLOWED_ORIGINS
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
FLAGFORGE_STORAGE_URL
```

### React
```
VITE_API_URL
VITE_APP_NAME
```
