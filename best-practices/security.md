# Security

## Security Checklist

### Backend
- [ ] All input validated with Pydantic
- [ ] Passwords hashed (bcrypt/pwdlib)
- [ ] JWT stored in httpOnly cookies (not localStorage)
- [ ] Refresh token rotation implemented
- [ ] Rate limiting enabled
- [ ] CORS properly configured
- [ ] SQL injection prevented
- [ ] Secrets from secrets manager (not plain env vars)
- [ ] 403 returned for unauthorized actions
- [ ] Stack traces not leaked in production
- [ ] Docs disabled in production
- [ ] Audit logging for sensitive actions
- [ ] Dependency vulnerability scanning in CI
- [ ] SameSite=Strict cookies (inherently prevents CSRF; explicit CSRF tokens only needed if cross-origin requests are required)

### Frontend
- [ ] No secrets in client code
- [ ] Input sanitization
- [ ] XSS prevention
- [ ] HTTPS only
- [ ] Security headers set
- [ ] **CSP (Content Security Policy)** header for XSS mitigation
- [ ] Dependency vulnerability scanning (npm audit, Dependabot)

---

## Authentication & Token Management

### JWT Storage
**Never store JWTs in localStorage** — vulnerable to XSS attacks.

**Correct approach: httpOnly cookies**
- Store access token in httpOnly cookie with `Secure` and `SameSite=Strict`
- Refresh token in separate httpOnly cookie
- Backend sets cookies on login, clears on logout

### Cookie-Based Auth Implementation (FastAPI)

```python
# core/security.py
from datetime import datetime, timedelta, timezone
from jose import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from app.core.config import settings  # provides settings.SECRET_KEY, settings.ALGORITHM

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM  # e.g. "HS256"

# pwdlib is the recommended replacement for the deprecated passlib library
# Install: pip install "pwdlib[bcrypt]"
pwd_hash = PasswordHash((BcryptHasher(),))

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_hash.verify(plain, hashed)

def hash_password(password: str) -> str:
    return pwd_hash.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
```

```python
# api/v1/endpoints/auth.py
from fastapi import APIRouter, Response, HTTPException, Depends, Cookie
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt
from app.db.session import get_db
from app.schemas.auth import LoginRequest
from app.core.security import (
    SECRET_KEY, ALGORITHM,
    create_access_token, create_refresh_token,
)
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService

router = APIRouter()

async def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db))

@router.post("/login")
async def login(
    data: LoginRequest,
    response: Response,
    service: UserService = Depends(get_user_service),
):
    # Delegate authentication to service layer (raises NotFoundError if invalid)
    user = await service.authenticate_user(data.email, data.password)

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    # Set httpOnly cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=15 * 60,  # 15 minutes
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=7 * 24 * 60 * 60,  # 7 days
    )

    return {"message": "Login successful"}  # No token in body - cookie is httpOnly

@router.post("/refresh")
async def refresh_tokens(
    response: Response,
    refresh_token: Annotated[str, Cookie()],
):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user id")
        new_access = create_access_token({"sub": user_id})
        new_refresh = create_refresh_token({"sub": user_id})

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    response.set_cookie(key="access_token", value=new_access, httponly=True, secure=True, samesite="strict", max_age=15 * 60)
    response.set_cookie(key="refresh_token", value=new_refresh, httponly=True, secure=True, samesite="strict", max_age=7 * 24 * 60 * 60)

    return {"message": "Tokens refreshed"}  # No token in body - cookies are httpOnly

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}
```

### React Cookie Auth Hook

```typescript
// hooks/useAuth.ts
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';

export function useAuth() {
  const queryClient = useQueryClient();
  const { data: user, isLoading, error } = useQuery({
    queryKey: ['currentUser'],
    queryFn: async () => {
      const response = await fetch('/api/v1/users/me', {
        credentials: 'include', // Send cookies
      });
      if (!response.ok) throw new Error('Not authenticated');
      return response.json();
    },
    retry: false,
  });

  const logout = async () => {
    await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'include' });
    queryClient.invalidateQueries({ queryKey: ['currentUser'] });
  };

  return { user, isLoading, error, logout, isAuthenticated: !!user };
}

// Protected route wrapper
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) return <div>Loading...</div>;
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return <>{children}</>;
}

// Usage
<ProtectedRoute>
  <Dashboard />
</ProtectedRoute>
```

### Refresh Token Rotation
- Access tokens: short-lived (15-30 minutes)
- Refresh tokens: longer-lived, rotated on each use
- On refresh: issue new access token + new refresh token
- **Revocation**: maintain token blacklist or use single-use refresh tokens
- Invalidate all tokens on password change or logout

### Token Invalidation Strategy
- **Logout**: client deletes cookies, server adds token to revocation list
- **Password change**: revoke all existing tokens for user
- **Admin action**: ability to revoke specific user sessions

---

## Secrets Management

### Don't Rely on Plain Environment Variables
Environment variables leak via:
- Crash dumps
- `ps aux` output
- Container inspection
- Log files

### Use a Secrets Manager
- **AWS Secrets Manager** or **Parameter Store**
- **HashiCorp Vault**
- **GCP Secret Manager**
- **Azure Key Vault**

### Pattern
```
Local dev: .env file (gitignored, never committed)
CI/CD:    Secrets injected at deploy time via secrets manager
Production: Secrets fetched at startup from secrets manager, cached
```
