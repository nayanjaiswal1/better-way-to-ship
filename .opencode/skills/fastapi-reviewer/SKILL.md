---
name: fastapi-reviewer
description: Review FastAPI code for best practices - async patterns, API design, performance, and validation
license: MIT
compatibility: opencode
metadata:
  audience: developers
  framework: FastAPI
---

## When to Use

Use this skill when reviewing FastAPI code. Load with: `skill({ name: "fastapi-reviewer" })`

## Review Checklist

### Project Structure (see `best-practices/fastapi.md`)
- Layered architecture: routes → services → repositories
- Proper dependency injection
- Centralized error handling

### API Design (see `best-practices/api-patterns.md`)
- RESTful endpoint design
- Proper HTTP methods and status codes
- Schema validation with Pydantic

### Performance (see `best-practices/fastapi.md#performance`)
- Async properly used (no blocking in async functions)
- Connection pooling configured
- Proper indexing strategy

### Security (see `best-practices/security.md`)
- Auth via HTTP-only cookies or Bearer tokens
- Input validation on all endpoints
- Rate limiting on public endpoints

### Background Tasks (see `best-practices/events.md`)
- Task queues for heavy operations
- Proper retry logic
- Idempotency keys for critical operations

### Testing (see `best-practices/testing.md`)
- pytest-asyncio for async tests
- API fixture patterns
- Integration tests for endpoints

## How to Review

1. Load relevant best-practice files
2. Check against checklist items
3. Provide specific fixes with file references
4. Flag security issues immediately

## Example Output

```
## FastAPI Best Practices Review

### ✅ Passed
- Proper Pydantic schemas
- Async endpoints correctly implemented

### ⚠️ Issues
- **Blocking call**: `requests.get()` in async endpoint
  Use `httpx.AsyncClient` instead
  See: best-practices/fastapi.md#performance
```
