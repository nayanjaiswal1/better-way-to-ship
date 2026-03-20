# Backend Internationalization (i18n)

Translate server-side strings: validation errors, email content, notification messages.
Frontend i18n (react-i18next) is covered in `frontend-advanced.md`.

## Supported Locales

```python
# common/i18n.py
SUPPORTED_LOCALES = ["en", "es", "fr", "de", "ja", "pt-BR"]
DEFAULT_LOCALE    = "en"

def normalize_locale(locale: str | None) -> str:
    """Map Accept-Language header to a supported locale."""
    if not locale:
        return DEFAULT_LOCALE
    # Exact match
    if locale in SUPPORTED_LOCALES:
        return locale
    # Language-only match (e.g. "pt" → "pt-BR")
    lang = locale.split("-")[0].split("_")[0]
    for supported in SUPPORTED_LOCALES:
        if supported.startswith(lang):
            return supported
    return DEFAULT_LOCALE
```

---

## Django — gettext

Django has built-in i18n using GNU gettext `.po` files.

### Setup

```python
# config/settings/base.py
from django.utils.translation import gettext_lazy as _

USE_I18N   = True
USE_L10N   = True
LANGUAGE_CODE = "en"

LANGUAGES = [
    ("en",    _("English")),
    ("es",    _("Spanish")),
    ("fr",    _("French")),
    ("de",    _("German")),
    ("ja",    _("Japanese")),
    ("pt-br", _("Portuguese (Brazil)")),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

MIDDLEWARE = [
    ...
    "django.middleware.locale.LocaleMiddleware",   # reads Accept-Language header
    ...
]
```

### Middleware — Read Locale from Request

```python
# common/middleware.py
from django.utils import translation
from common.i18n import normalize_locale

class LocaleMiddleware:
    """
    Activate locale from:
    1. User preference (stored in DB)
    2. Accept-Language header
    3. Default (en)
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, "locale"):
            locale = request.user.locale or self._from_header(request)
        else:
            locale = self._from_header(request)

        translation.activate(locale)
        request.LANGUAGE_CODE = locale
        response = self.get_response(request)
        translation.deactivate()
        return response

    def _from_header(self, request) -> str:
        header = request.headers.get("Accept-Language", "")
        # Parse "en-US,en;q=0.9,es;q=0.8" → "en"
        primary = header.split(",")[0].split(";")[0].strip()
        return normalize_locale(primary)
```

### Translating Strings

```python
# apps/orders/serializers.py
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

class OrderCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError(_("Amount must be greater than zero."))
        if value > 100000:
            raise serializers.ValidationError(_("Amount cannot exceed $100,000."))
        return value
```

```python
# apps/users/services.py
from django.utils.translation import gettext as _

def invite_user(email: str, tenant, inviter) -> User:
    if User.objects.filter(email=email, tenant=tenant).exists():
        raise AppValidationError(_("A user with this email already exists in your account."))
    ...
```

### Extract and Compile Translations

```bash
# Extract all translatable strings into .po files
django-admin makemessages -l es -l fr -l de -l ja -l pt_BR

# locale/es/LC_MESSAGES/django.po — send to translators
msgid "Amount must be greater than zero."
msgstr "El monto debe ser mayor que cero."

msgid "A user with this email already exists in your account."
msgstr "Ya existe un usuario con este correo en tu cuenta."

# Compile .po → .mo (binary, what Django actually reads)
django-admin compilemessages

# In CI — always compile before running
```

```makefile
# Makefile
i18n:extract:
	django-admin makemessages -l es -l fr -l de -l ja -l pt_BR --ignore="venv/*"

i18n:compile:
	django-admin compilemessages

i18n:check:
	# Fail if any .po file has untranslated strings (fuzz or empty msgstr)
	msgfmt --check locale/es/LC_MESSAGES/django.po
	msgfmt --check locale/fr/LC_MESSAGES/django.po
```

---

## FastAPI — Manual i18n

FastAPI has no built-in i18n. Use `Babel` + context variable.

```bash
pip install Babel
```

### Context Variable

```python
# core/i18n.py
from contextvars import ContextVar
from babel.support import Translations
from pathlib import Path

_current_locale: ContextVar[str] = ContextVar("locale", default="en")

_translations: dict[str, Translations] = {}

def load_translations():
    """Load all .mo files at startup."""
    locale_dir = Path("locale")
    for locale_dir_path in locale_dir.iterdir():
        if locale_dir_path.is_dir():
            locale = locale_dir_path.name
            t = Translations.load(locale_dir, [locale], domain="messages")
            _translations[locale] = t

def get_locale() -> str:
    return _current_locale.get()

def set_locale(locale: str) -> None:
    _current_locale.set(locale)

def _(text: str) -> str:
    """Translate text in the current locale."""
    locale = _current_locale.get()
    t = _translations.get(locale)
    if t:
        return t.gettext(text)
    return text

def ngettext(singular: str, plural: str, n: int) -> str:
    locale = _current_locale.get()
    t = _translations.get(locale)
    if t:
        return t.ngettext(singular, plural, n)
    return singular if n == 1 else plural
```

### Middleware

```python
# middleware/locale.py
from starlette.middleware.base import BaseHTTPMiddleware
from core.i18n import set_locale, normalize_locale

class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 1. User preference header (set by frontend from bootstrap)
        locale = request.headers.get("X-User-Locale")

        # 2. Accept-Language fallback
        if not locale:
            accept = request.headers.get("accept-language", "")
            primary = accept.split(",")[0].split(";")[0].strip()
            locale = normalize_locale(primary)

        set_locale(locale)
        return await call_next(request)

app.add_middleware(LocaleMiddleware)
```

### Translating Strings

```python
# services/order_service.py
from core.i18n import _

async def create_order(data: OrderCreate, user: User) -> Order:
    if data.amount <= 0:
        raise AppValidationError(_("Amount must be greater than zero."))
    ...
```

### Babel Message Extraction

```cfg
# babel.cfg
[python: **.py]
encoding = utf-8

[jinja2: **/templates/**.html]
encoding = utf-8
```

```bash
# Extract strings
pybabel extract -F babel.cfg -o locale/messages.pot .

# Initialize language files
pybabel init -i locale/messages.pot -d locale -l es
pybabel init -i locale/messages.pot -d locale -l fr

# Update after adding new strings
pybabel update -i locale/messages.pot -d locale

# Compile
pybabel compile -d locale
```

---

## User Locale Preference

```python
# Django — store locale on user model
class User(AbstractBaseUser, ...):
    locale = models.CharField(
        max_length=10,
        blank=True,
        choices=[(l, l) for l in SUPPORTED_LOCALES],
        default="",   # empty = use Accept-Language
    )

# API endpoint to update
class UserPreferencesView(APIView):
    def patch(self, request):
        locale = request.data.get("locale")
        if locale and locale not in SUPPORTED_LOCALES:
            raise AppValidationError(f"Unsupported locale: {locale}")
        request.user.locale = locale or ""
        request.user.save(update_fields=["locale", "updated_at"])
        return Response({"locale": request.user.locale})
```

```tsx
// React — send user's locale with every request
// Set once in bootstrap, then X-User-Locale header on all requests

const { i18n } = useTranslation();

// In API client setup
apiClient.defaults.headers["X-User-Locale"] = i18n.language;

// Or in the bootstrap response — backend sets user.locale
const { mutate: updateLocale } = useMutation({
  mutationFn: (locale: string) => api.patch("/users/me/preferences", { locale }),
  onSuccess: () => i18n.changeLanguage(locale),
});
```

---

## Translating Emails

```python
# apps/notifications/tasks.py
from django.utils.translation import activate, deactivate
from django.template.loader import render_to_string

def send_localized_email(user, template: str, context: dict) -> None:
    """Render email in the user's locale, not the current request locale."""
    locale = user.locale or "en"

    # Temporarily activate user's locale for this task
    activate(locale)
    try:
        html = render_to_string(f"emails/{template}.html", context)
        text = render_to_string(f"emails/{template}.txt",  context)
    finally:
        deactivate()

    send_transactional_email(to=user.email, subject=..., html=html, text=text)
```

---

## Localized Validation Errors — DRF

DRF validation errors are automatically translated if Django's `LocaleMiddleware` is active.

```python
# Override DRF built-in messages for consistency
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

class EmailField(serializers.EmailField):
    default_error_messages = {
        "invalid": _("Enter a valid email address."),
        "required": _("Email address is required."),
    }
```

---

## i18n Checklist

### Django
- [ ] `USE_I18N = True` and `LOCALE_PATHS` configured
- [ ] `LocaleMiddleware` in `MIDDLEWARE` — activates locale per request
- [ ] All user-visible strings wrapped in `_()` or `gettext_lazy()`
- [ ] `.po` files committed to git — compiled `.mo` files in CI, not committed
- [ ] `compilemessages` runs in CI before tests
- [ ] Celery tasks use `activate(user.locale)` — not request locale

### FastAPI
- [ ] `LocaleMiddleware` reads `X-User-Locale` header then `Accept-Language`
- [ ] Translations loaded at startup via `load_translations()`
- [ ] All user-visible strings wrapped in `_()`
- [ ] Babel extract + compile in CI

### Both
- [ ] User locale preference stored in DB — survives across sessions
- [ ] Emails rendered in recipient's locale — not the sender's request locale
- [ ] `SUPPORTED_LOCALES` list centralized — validated on user preference update
- [ ] Frontend sends `X-User-Locale` header on all requests (from `i18n.language`)
- [ ] New translatable strings flagged in PR — don't merge untranslated
