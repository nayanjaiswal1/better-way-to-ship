# Developer Experience

## Git Hooks — Enforce Quality Before Commit

Catch issues locally before CI — faster feedback, no wasted pipeline runs.

```bash
# pip install pre-commit
# pre-commit install  ← run once after clone
```

```yaml
# .pre-commit-config.yaml
repos:
  # Python
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff           # lint
        args: [--fix]
      - id: ruff-format    # format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]

  # JavaScript/TypeScript
  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v9.0.0
    hooks:
      - id: eslint
        files: \.(ts|tsx)$
        additional_dependencies:
          - eslint
          - typescript
          - '@typescript-eslint/parser'

  # General
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-merge-conflict
      - id: check-added-large-files
        args: ['--maxkb=500']
      - id: no-commit-to-branch
        args: ['--branch', 'main', '--branch', 'master']
      - id: trailing-whitespace
      - id: end-of-file-fixer
```

---

## Makefile — One Command for Everything

```makefile
# Makefile
.PHONY: install dev test lint format migrate shell

# Setup
install:
	pip install -r requirements.txt
	npm install --prefix frontend
	pre-commit install

# Development
dev:
	docker compose up -d db redis
	uvicorn app.main:app --reload --port 8000 &
	npm run dev --prefix frontend

# Testing
test:
	pytest tests/ -v --cov=app --cov-report=term-missing

test-watch:
	pytest tests/ -v --watch

test-frontend:
	npm run test --prefix frontend

# Code quality
lint:
	ruff check .
	mypy app/
	npm run lint --prefix frontend

format:
	ruff format .
	npm run format --prefix frontend

# Database
migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(name)"

migrate-rollback:
	alembic downgrade -1

seed:
	python scripts/seed_db.py

# Utilities
shell:
	python -c "import asyncio; from app.db.session import get_db; asyncio.run(main())"

logs:
	docker compose logs -f api

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .ruff_cache .mypy_cache
```

---

## Local Dev Setup

### Docker Compose — services only (DB, Redis, etc.)

Run services in Docker, app code locally for fast reload:

```yaml
# docker-compose.dev.yml
services:
  db:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: myapp_dev
    volumes:
      - postgres_dev_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dev -d myapp_dev"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  mailpit:                   # local email testing — catches all sent emails
    image: axllent/mailpit
    ports:
      - "1025:1025"          # SMTP
      - "8025:8025"          # Web UI at http://localhost:8025

volumes:
  postgres_dev_data:
```

### .env.example — always keep updated

```bash
# .env.example — committed to git, actual .env is gitignored
APP_NAME=MyApp
DEBUG=true
SECRET_KEY=change-me-in-production

DATABASE_URL=postgresql+asyncpg://dev:dev@localhost:5432/myapp_dev
REDIS_URL=redis://localhost:6379/0

SMTP_HOST=localhost
SMTP_PORT=1025

AWS_REGION=us-east-1
S3_BUCKET=myapp-dev
```

### Onboarding script — new dev setup in one command

```bash
#!/bin/bash
# scripts/setup.sh

set -e

echo "Setting up development environment..."

# Copy env
cp .env.example .env
echo "✓ Created .env from .env.example"

# Python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
echo "✓ Python dependencies installed"

# Frontend
npm install --prefix frontend
echo "✓ Node dependencies installed"

# Git hooks
pre-commit install
echo "✓ Git hooks installed"

# Start services
docker compose -f docker-compose.dev.yml up -d
echo "✓ Services started"

# Wait for DB
sleep 3
alembic upgrade head
python scripts/seed_db.py
echo "✓ Database migrated and seeded"

echo ""
echo "Ready! Run: make dev"
```

---

## Database Backup Strategy

### Automated backups — never rely on cloud provider alone

```bash
#!/bin/bash
# scripts/backup_db.sh — run via cron or CI

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="backup_${TIMESTAMP}.sql.gz"
S3_PATH="s3://${BACKUP_BUCKET}/postgres/${BACKUP_FILE}"

# Dump and compress
pg_dump "${DATABASE_URL}" | gzip > "/tmp/${BACKUP_FILE}"

# Upload to S3
aws s3 cp "/tmp/${BACKUP_FILE}" "${S3_PATH}" \
  --storage-class STANDARD_IA

# Cleanup local file
rm "/tmp/${BACKUP_FILE}"

echo "Backup complete: ${S3_PATH}"
```

```yaml
# .github/workflows/backup.yml
name: Database Backup
on:
  schedule:
    - cron: '0 2 * * *'  # daily at 2am UTC

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run backup
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          BACKUP_BUCKET: ${{ secrets.BACKUP_BUCKET }}
        run: bash scripts/backup_db.sh
```

### Restore testing — monthly

```bash
#!/bin/bash
# scripts/test_restore.sh — verify backups actually work

LATEST=$(aws s3 ls s3://${BACKUP_BUCKET}/postgres/ | sort | tail -1 | awk '{print $4}')
aws s3 cp "s3://${BACKUP_BUCKET}/postgres/${LATEST}" /tmp/restore_test.sql.gz

# Restore to test DB
createdb myapp_restore_test
gunzip -c /tmp/restore_test.sql.gz | psql myapp_restore_test

# Verify row counts
psql myapp_restore_test -c "SELECT COUNT(*) FROM users;" > /dev/null

# Cleanup
dropdb myapp_restore_test
rm /tmp/restore_test.sql.gz

echo "Restore test passed ✓"
```

### Retention policy

```
Daily backups   → keep 7 days
Weekly backups  → keep 4 weeks
Monthly backups → keep 12 months
```

```bash
# Lifecycle policy in S3 (set once via Terraform/console)
# daily/   → expire after 7 days
# weekly/  → expire after 28 days
# monthly/ → expire after 365 days
```

---

## CORS Configuration

```python
# main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,   # ["https://app.example.com"]
    allow_credentials=True,                   # required for httpOnly cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
)

# core/config.py
class Settings(BaseSettings):
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]  # dev default

    @validator("ALLOWED_ORIGINS", pre=True)
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",")]
        return v
```

## CSP Headers

```python
# middleware/security_headers.py
from fastapi import Request

async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.example.com; "
        "font-src 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

# main.py
app.middleware("http")(security_headers_middleware)
```
