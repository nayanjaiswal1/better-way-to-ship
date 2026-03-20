---
name: django-reviewer
description: Review Django code for best practices - patterns, security, performance, and maintainability
license: MIT
compatibility: opencode
metadata:
  audience: developers
  framework: Django
---

## When to Use

Use this skill when reviewing Django code. Load with: `skill({ name: "django-reviewer" })`

## Review Checklist

### Project Structure
- Follows Django project layout from `best-practices/django.md`
- Uses repository pattern for data access
- Proper app separation

### Security (see `best-practices/security.md`, `best-practices/django-permissions.md`)
- No raw SQL queries
- Proper permission classes on views
- Auth via JWT cookies, not tokens in localStorage
- CSRF protection enabled

### API / Views (see `best-practices/django.md`)
- Uses DRF ViewSets properly
- Serializers validate all input
- No N+1 queries - use select_related/prefetch_related

### Background Tasks (see `best-practices/django-celery.md`)
- Tasks are idempotent
- Uses on_commit for transaction safety
- Proper retry logic

### Testing (see `best-practices/django-testing.md`)
- Factory Boy for test fixtures
- Test client for API tests
- Coverage targets 80%+

### Performance (see `best-practices/django-resilience.md`)
- Throttling configured on public endpoints
- Database indexes on foreign keys and frequently queried fields
- No queries in templates

## How to Review

1. Read the relevant best-practice files for context
2. Check code against each checklist item
3. Provide specific, actionable feedback
4. Reference the best-practice file for more details

## Example Output

```
## Django Best Practices Review

### ✅ Passed
- Using DRF ViewSets correctly
- Proper serializer validation

### ⚠️ Needs Improvement
- **N+1 Query**: `author.posts.all()` in loop → Use prefetch_related
  See: best-practices/django.md#orm-patterns

### ❌ Issues
- **Security**: Passwords logged in plain text
  Fix: best-practices/security.md#passwords
```
