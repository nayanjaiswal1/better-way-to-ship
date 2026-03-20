# OpenAPI Contract-First Development

## Generate TypeScript Types from OpenAPI

Single source of truth: FastAPI schema → TypeScript types. No manual type sync.

```bash
# Install generator
npm install --save-dev openapi-typescript

# Generate types from running server
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts

# Or from saved spec file
npx openapi-typescript openapi.json -o src/api/schema.d.ts
```

```json
// package.json — generate types as part of dev workflow
{
  "scripts": {
    "api:types": "openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts",
    "api:types:ci": "openapi-typescript openapi.json -o src/api/schema.d.ts"
  }
}
```

### Generated types

FastAPI automatically generates OpenAPI from Pydantic models. Types flow: **Pydantic → OpenAPI → TypeScript**.

```python
# FastAPI — Pydantic model is the source of truth
class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: Literal["admin", "member", "viewer"]
    created_at: datetime
```

```typescript
// src/api/schema.d.ts — auto-generated, never edit manually
export interface components {
  schemas: {
    UserResponse: {
      id: string;
      name: string;
      email: string;
      role: "admin" | "member" | "viewer";
      created_at: string;
    };
  };
}
```

---

## Type-Safe API Client

Use generated types with a thin fetch wrapper — no `any`, no casting.

```bash
npm install openapi-fetch
```

```typescript
// src/api/client.ts — typed fetch client
import createClient from 'openapi-fetch';
import type { paths } from './schema.d.ts';

export const apiClient = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL ?? '',
  credentials: 'include',  // send httpOnly cookies
});

// Every call is fully typed — no casting
const { data, error } = await apiClient.GET('/api/v1/users/{id}', {
  params: { path: { id: userId } },
});
// data is typed as UserResponse | undefined
// error is typed as ErrorResponse | undefined
```

```typescript
// src/api/users.ts — typed API functions
import { apiClient } from './client';
import type { components } from './schema.d.ts';

type UserResponse = components['schemas']['UserResponse'];
type UserCreate   = components['schemas']['UserCreate'];

export const usersApi = {
  async getMe(): Promise<UserResponse> {
    const { data, error } = await apiClient.GET('/api/v1/users/me');
    if (error) throw new Error(error.detail as string);
    return data!;
  },

  async create(body: UserCreate): Promise<UserResponse> {
    const { data, error } = await apiClient.POST('/api/v1/users', { body });
    if (error) throw new Error(error.detail as string);
    return data!;
  },

  async list(params?: { page?: number; page_size?: number }) {
    const { data, error } = await apiClient.GET('/api/v1/users', {
      params: { query: params },
    });
    if (error) throw new Error(error.detail as string);
    return data!;
  },
};
```

---

## Export OpenAPI Spec in CI

Save the spec as an artifact — used for type generation and contract testing.

```python
# scripts/export_openapi.py — run as part of CI
import json
from app.main import app

spec = app.openapi()
with open("openapi.json", "w") as f:
    json.dump(spec, f, indent=2)

print(f"Exported {len(spec['paths'])} paths")
```

```yaml
# .github/workflows/ci.yml
- name: Export OpenAPI spec
  run: |
    # Start server briefly to extract spec
    python scripts/export_openapi.py

- name: Generate TypeScript types
  run: npx openapi-typescript openapi.json -o frontend/src/api/schema.d.ts

- name: Check for uncommitted type changes
  run: |
    git diff --exit-code frontend/src/api/schema.d.ts || \
      (echo "TypeScript types are out of sync with backend schema. Run 'npm run api:types'." && exit 1)

- name: Upload OpenAPI spec
  uses: actions/upload-artifact@v4
  with:
    name: openapi-spec
    path: openapi.json
```

---

## Contract Testing — Schemathesis

Automatically test every API endpoint against its own OpenAPI spec.

```bash
pip install schemathesis
```

```bash
# Run against local server
schemathesis run http://localhost:8000/openapi.json \
  --auth-type cookie \
  --header "Cookie: access_token=<test_token>" \
  --checks all \
  --stateful=links   # follow links between responses

# Run in CI against staging
schemathesis run https://staging.api.example.com/openapi.json \
  --checks all \
  --max-examples 50  # 50 random examples per endpoint
```

```yaml
# .github/workflows/contract-tests.yml
name: Contract Tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  contract:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
        options: --health-cmd pg_isready

    steps:
      - uses: actions/checkout@v4

      - name: Start API
        run: |
          pip install -r requirements.txt
          uvicorn app.main:app --host 0.0.0.0 --port 8000 &
          sleep 5
        env:
          DATABASE_URL: postgresql://postgres:test@localhost/test
          TESTING: "true"

      - name: Run contract tests
        run: |
          pip install schemathesis
          schemathesis run http://localhost:8000/openapi.json \
            --checks all \
            --max-examples 30 \
            --hypothesis-seed 42  # reproducible
```

---

## Versioned Spec — Track Breaking Changes

```bash
# oasdiff — detect breaking changes between spec versions
npm install -g @oasdiff/oasdiff

# Compare main branch spec with PR spec
oasdiff breaking \
  https://raw.githubusercontent.com/myorg/myapp/main/openapi.json \
  openapi.json

# Output:
# GET /api/v1/users/{id} response property 'email' became required (breaking)
# DELETE /api/v1/posts/{id} removed (breaking)
```

```yaml
# .github/workflows/ci.yml
- name: Check for breaking API changes
  run: |
    # Download spec from main branch
    curl -o openapi-main.json \
      https://raw.githubusercontent.com/${{ github.repository }}/main/openapi.json

    # Compare against PR spec
    npx @oasdiff/oasdiff breaking openapi-main.json openapi.json \
      --fail-on ERR  # fail CI on breaking changes
```

---

## FastAPI — OpenAPI Customization

```python
# main.py — enrich the spec
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="MyApp API",
    version="1.0.0",
    description="Production-ready FastAPI + React application",
    docs_url=None,           # disable in production
    redoc_url=None,
    openapi_url="/openapi.json",
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Add security scheme for cookie auth
    schema["components"]["securitySchemes"] = {
        "cookieAuth": {
            "type": "apiKey",
            "in": "cookie",
            "name": "access_token",
        }
    }

    # Apply security globally
    schema["security"] = [{"cookieAuth": []}]

    # Add contact and license info
    schema["info"]["contact"] = {
        "name": "API Support",
        "email": "api@example.com",
    }

    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi
```

```python
# Tag and document every endpoint
@router.get(
    "/users/{id}",
    response_model=UserResponse,
    summary="Get user by ID",
    description="Fetch a single user. Tenants can only access their own users.",
    responses={
        200: {"description": "User found"},
        403: {"description": "Access denied — not your tenant"},
        404: {"description": "User not found"},
    },
    tags=["users"],
)
async def get_user(id: str): ...
```

---

## Workflow Summary

```
1. Backend changes Pydantic model
        ↓
2. FastAPI auto-updates /openapi.json
        ↓
3. CI exports openapi.json as artifact
        ↓
4. CI checks for breaking changes (oasdiff)
        ↓
5. CI generates TypeScript types
        ↓
6. CI checks types are committed (no drift)
        ↓
7. Contract tests (Schemathesis) validate spec is correct
        ↓
8. Frontend uses typed client — no casting, no surprises
```

---

## Checklist

- [ ] `openapi-typescript` generates types on every CI run
- [ ] TypeScript types committed and drift check in CI (fails if stale)
- [ ] `openapi-fetch` used for API calls — no raw `fetch` with casting
- [ ] `oasdiff` detects breaking changes on every PR
- [ ] Schemathesis contract tests in CI
- [ ] Every endpoint has `summary`, `description`, `responses` documented
- [ ] Security scheme documented in spec
- [ ] `/openapi.json` disabled in production (`openapi_url=None`)
- [ ] OpenAPI spec saved as CI artifact for downstream consumers
