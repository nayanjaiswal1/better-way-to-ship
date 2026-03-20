---
name: api-designer
description: Design robust REST APIs - endpoints, versioning, error handling, and documentation
license: MIT
compatibility: opencode
metadata:
  audience: backend-developers
  scope: api-design
---

## When to Use

Use this skill when designing or reviewing APIs. Load with: `skill({ name: "api-designer" })`

## API Design Principles (see `best-practices/api-patterns.md`)

### REST Conventions
- Resource-based URLs: `/users`, `/posts/{id}`
- Proper HTTP methods: GET (read), POST (create), PUT/PATCH (update), DELETE
- Status codes: 200, 201, 400, 401, 403, 404, 500

### Schema Design (see `best-practices/api-patterns.md#schema`)
- Separate data from schema
- Use schemas for request/response
- Field selection with `fields` parameter
- Pagination with cursor-based (not offset)

### Error Handling
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human readable message",
    "details": [...]
  }
}
```
- Never expose stack traces
- Log errors server-side

### Versioning (see `best-practices/api-patterns.md#versioning`)
- URL versioning: `/api/v1/`
- Header versioning for microservices
- Maintain backwards compatibility

### Performance (see `best-practices/api-patterns.md`)
- ETag support for caching
- Idempotency keys for POST requests
- Prefetching related resources
- Compression enabled

### Documentation
- OpenAPI/Swagger spec
- Example requests/responses
- Error code documentation

## API Checklist

### ✅ Required
- [ ] Authentication (JWT/HTTP-only cookie)
- [ ] Authorization (ownership checks)
- [ ] Input validation (Pydantic/Django serializers)
- [ ] Rate limiting
- [ ] Proper error responses
- [ ] OpenAPI docs

### ⚡ Performance
- [ ] Database indexes
- [ ] Connection pooling
- [ ] Response compression
- [ ] ETag/Last-Modified headers

### 🔒 Security
- [ ] HTTPS only
- [ ] CORS configured
- [ ] Security headers
- [ ] No sensitive data in URLs

## Example Output

```
## API Design Review

### Endpoint: POST /api/v1/posts

✅ Correct:
- 201 Created on success
- Location header with new resource
- Idempotency key supported

❌ Issues:
- Missing rate limit
- Error response missing code field
- No OpenAPI documentation

### Recommended Fix:
See best-practices/api-patterns.md#error-handling
```
