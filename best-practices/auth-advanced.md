# Advanced Auth — OAuth / SSO & 2FA

## OAuth / SSO

### Backend — Google + GitHub (authlib)

```bash
pip install authlib httpx
```

```python
# core/oauth.py
from authlib.integrations.httpx_client import AsyncOAuth2Client
from app.core.config import settings

GOOGLE_CONFIG = {
    "client_id": settings.GOOGLE_CLIENT_ID,
    "client_secret": settings.GOOGLE_CLIENT_SECRET,
    "authorize_url": "https://accounts.google.com/o/oauth2/auth",
    "token_url": "https://oauth2.googleapis.com/token",
    "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
    "scopes": ["openid", "email", "profile"],
}

GITHUB_CONFIG = {
    "client_id": settings.GITHUB_CLIENT_ID,
    "client_secret": settings.GITHUB_CLIENT_SECRET,
    "authorize_url": "https://github.com/login/oauth/authorize",
    "token_url": "https://github.com/login/oauth/access_token",
    "userinfo_url": "https://api.github.com/user",
    "scopes": ["read:user", "user:email"],
}

PROVIDERS = {"google": GOOGLE_CONFIG, "github": GITHUB_CONFIG}
```

```python
# api/v1/endpoints/oauth.py
from fastapi import APIRouter, Response, HTTPException
from authlib.integrations.httpx_client import AsyncOAuth2Client
from app.core.oauth import PROVIDERS
from app.services.user_service import UserService
from app.core.security import create_access_token, create_refresh_token
import secrets

router = APIRouter()

# In-memory state store — use Redis in production
_states: dict[str, str] = {}

@router.get("/{provider}/authorize")
async def oauth_authorize(provider: str):
    """Step 1 — redirect user to provider login page."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")

    config = PROVIDERS[provider]
    state = secrets.token_urlsafe(32)
    _states[state] = provider

    async with AsyncOAuth2Client(
        client_id=config["client_id"],
        scope=" ".join(config["scopes"]),
        redirect_uri=f"{settings.APP_URL}/api/v1/oauth/{provider}/callback",
    ) as client:
        url, _ = client.create_authorization_url(config["authorize_url"], state=state)

    return {"authorization_url": url}

@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    response: Response,
    service: UserService = Depends(get_user_service),
):
    """Step 2 — exchange code for token, get user info, log in."""
    if _states.pop(state, None) != provider:
        raise HTTPException(status_code=400, detail="Invalid state")

    config = PROVIDERS[provider]

    async with AsyncOAuth2Client(
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        redirect_uri=f"{settings.APP_URL}/api/v1/oauth/{provider}/callback",
    ) as client:
        token = await client.fetch_token(config["token_url"], code=code)
        userinfo_resp = await client.get(config["userinfo_url"])
        userinfo = userinfo_resp.json()

    # Get or create user
    email = userinfo.get("email")
    name = userinfo.get("name") or userinfo.get("login")  # GitHub uses login
    user = await service.get_or_create_oauth_user(email=email, name=name, provider=provider)

    # Set auth cookies — same as password login
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="strict", max_age=15*60)
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=True, samesite="strict", max_age=7*24*60*60)

    # Redirect to frontend
    return Response(status_code=302, headers={"Location": f"{settings.FRONTEND_URL}/dashboard"})
```

```python
# services/user_service.py
async def get_or_create_oauth_user(self, email: str, name: str, provider: str) -> User:
    user = await self.repo.get_by_email(email)
    if user:
        return user  # existing user — log them in

    # New user via OAuth — no password
    return await self.repo.create(User(
        email=email,
        name=name,
        oauth_provider=provider,
        hashed_password=None,  # no password for OAuth users
    ))
```

### React — OAuth buttons

```tsx
// components/OAuthButtons.tsx
function OAuthButtons() {
  const handleOAuth = async (provider: 'google' | 'github') => {
    const { authorization_url } = await fetch(
      `/api/v1/oauth/${provider}/authorize`,
      { credentials: 'include' }
    ).then(r => r.json());

    window.location.href = authorization_url;  // redirect to provider
  };

  return (
    <div>
      <button onClick={() => handleOAuth('google')}>
        Continue with Google
      </button>
      <button onClick={() => handleOAuth('github')}>
        Continue with GitHub
      </button>
    </div>
  );
}
```

---

## 2FA / MFA (TOTP)

Time-based One-Time Passwords — compatible with Google Authenticator, Authy, 1Password.

```bash
pip install pyotp qrcode[pil]
```

### Backend

```python
# core/totp.py
import pyotp
import qrcode
import io, base64

def generate_totp_secret() -> str:
    return pyotp.random_base32()

def get_totp_uri(secret: str, email: str, issuer: str = "MyApp") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)

def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)  # allow 30s clock drift

def generate_qr_code_b64(uri: str) -> str:
    """Returns base64 PNG for display in React."""
    img = qrcode.make(uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()
```

```python
# api/v1/endpoints/mfa.py
import secrets as secrets_module
from app.core.totp import generate_totp_secret, get_totp_uri, verify_totp, generate_qr_code_b64

router = APIRouter()

@router.post("/mfa/setup")
async def setup_mfa(current_user=Depends(get_current_user), service=Depends(get_user_service)):
    """Step 1 — generate secret and QR code."""
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, current_user.email)
    qr_code = generate_qr_code_b64(uri)

    # Store secret temporarily (not activated until verified)
    await service.store_pending_mfa_secret(current_user.id, secret)

    return {"qr_code": f"data:image/png;base64,{qr_code}", "secret": secret}

@router.post("/mfa/verify")
async def verify_mfa_setup(
    code: str,
    current_user=Depends(get_current_user),
    service=Depends(get_user_service),
):
    """Step 2 — verify code to activate MFA."""
    secret = await service.get_pending_mfa_secret(current_user.id)
    if not secret or not verify_totp(secret, code):
        raise AppValidationError("Invalid code")

    backup_codes = [secrets_module.token_hex(4) for _ in range(8)]  # 8 backup codes
    await service.activate_mfa(current_user.id, secret, backup_codes)

    return {"backup_codes": backup_codes}  # show ONCE — never again

@router.post("/mfa/validate")
async def validate_mfa(
    code: str,
    current_user=Depends(get_current_user),
    service=Depends(get_user_service),
):
    """Called during login if user has MFA enabled."""
    user = await service.get_user(current_user.id)

    # Try TOTP code first, then backup codes
    if verify_totp(user.mfa_secret, code):
        return {"valid": True}

    if await service.use_backup_code(current_user.id, code):
        return {"valid": True, "backup_code_used": True}

    raise AppValidationError("Invalid MFA code")

@router.delete("/mfa/disable")
async def disable_mfa(
    code: str,
    current_user=Depends(get_current_user),
    service=Depends(get_user_service),
):
    """Require valid code to disable MFA — prevents account takeover."""
    user = await service.get_user(current_user.id)
    if not verify_totp(user.mfa_secret, code):
        raise ForbiddenError("Invalid MFA code")
    await service.disable_mfa(current_user.id)
    return {"message": "MFA disabled"}
```

### React — MFA Setup Flow

```tsx
// components/MFASetup.tsx
function MFASetup() {
  const [step, setStep] = useState<'setup' | 'verify' | 'backup'>('setup');
  const [qrCode, setQrCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [code, setCode] = useState('');

  const setup = useMutation({
    mutationFn: () =>
      fetch('/api/v1/mfa/setup', { method: 'POST', credentials: 'include' }).then(r => r.json()),
    onSuccess: (data) => {
      setQrCode(data.qr_code);
      setStep('verify');
    },
  });

  const verify = useMutation({
    mutationFn: (code: string) =>
      fetch(`/api/v1/mfa/verify?code=${code}`, { method: 'POST', credentials: 'include' }).then(r => r.json()),
    onSuccess: (data) => {
      setBackupCodes(data.backup_codes);
      setStep('backup');
    },
  });

  if (step === 'setup') return <button onClick={() => setup.mutate()}>Enable 2FA</button>;

  if (step === 'verify') return (
    <div>
      <img src={qrCode} alt="Scan with authenticator app" />
      <input value={code} onChange={e => setCode(e.target.value)} placeholder="Enter 6-digit code" />
      <button onClick={() => verify.mutate(code)}>Verify</button>
    </div>
  );

  if (step === 'backup') return (
    <div>
      <p>Save these backup codes — shown only once:</p>
      {backupCodes.map(c => <code key={c}>{c}</code>)}
    </div>
  );
}
```

### Model Changes

```python
# models/user.py — add MFA fields
class User(Base, SoftDeleteMixin):
    mfa_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(default=False)
    mfa_backup_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    pending_mfa_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
```
