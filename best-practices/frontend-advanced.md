# Frontend Advanced Patterns

## i18n (Internationalization)

### Setup — react-i18next

```bash
npm install react-i18next i18next i18next-http-backend i18next-browser-languagedetector
```

```tsx
// i18n/index.ts — configure once, never touch again
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import HttpBackend from 'i18next-http-backend';
import LanguageDetector from 'i18next-browser-languagedetector';

i18n
  .use(HttpBackend)             // loads translations from /locales/{lng}/{ns}.json
  .use(LanguageDetector)        // detects browser language
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    supportedLngs: ['en', 'es', 'fr', 'de'],
    ns: ['common', 'errors', 'auth'],
    defaultNS: 'common',
    backend: {
      loadPath: '/locales/{{lng}}/{{ns}}.json',
    },
    interpolation: {
      escapeValue: false,  // React already escapes
    },
  });

export default i18n;
```

```
public/locales/
├── en/
│   ├── common.json    { "save": "Save", "cancel": "Cancel" }
│   ├── errors.json    { "not_found": "Resource not found" }
│   └── auth.json      { "login": "Sign in", "logout": "Sign out" }
├── es/
│   ├── common.json    { "save": "Guardar", "cancel": "Cancelar" }
│   └── ...
```

```tsx
// main.tsx
import './i18n';  // import before App

// Usage — never hardcode strings
function SaveButton() {
  const { t } = useTranslation('common');
  return <button>{t('save')}</button>;
}

// Interpolation
function WelcomeMessage({ name }: { name: string }) {
  const { t } = useTranslation();
  return <p>{t('welcome', { name })}</p>;
  // en: "Welcome, {{name}}!" → "Welcome, John!"
}

// Language switcher — write once
function LanguageSwitcher() {
  const { i18n } = useTranslation();
  return (
    <select
      value={i18n.language}
      onChange={(e) => i18n.changeLanguage(e.target.value)}
    >
      <option value="en">English</option>
      <option value="es">Español</option>
      <option value="fr">Français</option>
    </select>
  );
}
```

### Backend — locale-aware responses

```python
# Middleware reads Accept-Language header
from fastapi import Request

async def locale_middleware(request: Request, call_next):
    locale = request.headers.get("Accept-Language", "en").split(",")[0].split("-")[0]
    request.state.locale = locale if locale in ["en", "es", "fr"] else "en"
    return await call_next(request)

# Error messages in user's language
class NotFoundError(AppError):
    def __init__(self, resource: str, locale: str = "en"):
        messages = {
            "en": f"{resource} not found",
            "es": f"{resource} no encontrado",
        }
        super().__init__(messages.get(locale, messages["en"]), "NOT_FOUND")
```

---

## Image Optimization

### Lazy loading — never load off-screen images

```tsx
// ✅ Native lazy loading — works in all modern browsers
<img
  src="/images/product.jpg"
  alt="Product"
  loading="lazy"          // browser loads only when near viewport
  decoding="async"        // don't block main thread
/>

// ✅ With blur placeholder — no layout shift
function ProductImage({ src, alt }: { src: string; alt: string }) {
  const [loaded, setLoaded] = useState(false);

  return (
    <div className="relative">
      {!loaded && <div className="skeleton-placeholder" />}
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        onLoad={() => setLoaded(true)}
        className={loaded ? 'opacity-100' : 'opacity-0'}
        style={{ transition: 'opacity 0.3s' }}
      />
    </div>
  );
}
```

### Responsive images — serve correct size

```tsx
// ✅ Browser picks the right size automatically
<img
  src="/images/hero.jpg"
  srcSet="
    /images/hero-400.webp 400w,
    /images/hero-800.webp 800w,
    /images/hero-1200.webp 1200w
  "
  sizes="(max-width: 600px) 400px, (max-width: 1024px) 800px, 1200px"
  alt="Hero"
  loading="lazy"
/>
```

### Backend — S3 + CloudFront for images

```python
# services/upload_service.py
import boto3
from ulid import ULID

s3 = boto3.client("s3", region_name=settings.AWS_REGION)

def generate_presigned_upload_url(
    filename: str,
    content_type: str,
    max_size_bytes: int = 10 * 1024 * 1024,  # 10MB
) -> dict:
    key = f"uploads/{ULID()}/{filename}"

    url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.S3_BUCKET,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": max_size_bytes,
        },
        ExpiresIn=300,  # 5 minutes
    )
    return {"upload_url": url, "key": key}

# api/v1/endpoints/uploads.py
@router.post("/uploads/presign")
async def presign_upload(
    filename: str,
    content_type: str,
    current_user=Depends(get_current_user),
):
    """Client uploads directly to S3 — backend never proxies the file."""
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if content_type not in allowed_types:
        raise AppValidationError("Invalid file type")

    return generate_presigned_upload_url(filename, content_type)
```

```tsx
// React — direct S3 upload
async function uploadImage(file: File): Promise<string> {
  // 1. Get presigned URL from backend
  const { upload_url, key } = await fetch('/api/v1/uploads/presign', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: file.name, content_type: file.type }),
  }).then(r => r.json());

  // 2. Upload directly to S3 — no backend involved
  await fetch(upload_url, {
    method: 'PUT',
    body: file,
    headers: { 'Content-Type': file.type },
  });

  // 3. Return CDN URL
  return `${CDN_BASE_URL}/${key}`;
}

function ImageUploader() {
  const [uploading, setUploading] = useState(false);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    const url = await uploadImage(file);
    setUploading(false);
    // use url...
  };

  return (
    <label>
      {uploading ? 'Uploading...' : 'Upload Image'}
      <input type="file" accept="image/*" onChange={handleFile} hidden />
    </label>
  );
}
```

---

## Multi-Step Forms

Wizard pattern — state persisted across steps, validated per step.

```tsx
// hooks/useMultiStepForm.ts
import { useState } from 'react';
import { useForm, UseFormReturn } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

// Define schema per step
const step1Schema = z.object({ name: z.string().min(1), email: z.string().email() });
const step2Schema = z.object({ plan: z.enum(['free', 'pro', 'enterprise']) });
const step3Schema = z.object({ cardToken: z.string().min(1) });

const schemas = [step1Schema, step2Schema, step3Schema];

export function useMultiStepForm(totalSteps: number) {
  const [step, setStep] = useState(0);
  const [formData, setFormData] = useState({});

  const form = useForm({
    resolver: zodResolver(schemas[step]),
    defaultValues: formData,
  });

  const next = form.handleSubmit((data) => {
    setFormData(prev => ({ ...prev, ...data }));  // accumulate data
    setStep(s => Math.min(s + 1, totalSteps - 1));
  });

  const back = () => setStep(s => Math.max(s - 1, 0));

  return { step, form, next, back, formData, isFirst: step === 0, isLast: step === totalSteps - 1 };
}

// OnboardingWizard.tsx
function OnboardingWizard() {
  const { step, form, next, back, formData, isFirst, isLast } = useMultiStepForm(3);
  const createAccount = useMutation({ mutationFn: submitOnboarding });

  const steps = [
    <Step1 form={form} />,
    <Step2 form={form} />,
    <Step3 form={form} />,
  ];

  const handleFinish = form.handleSubmit(async (data) => {
    await createAccount.mutateAsync({ ...formData, ...data });
  });

  return (
    <div>
      <ProgressBar current={step + 1} total={3} />
      {steps[step]}
      <div>
        {!isFirst && <button onClick={back}>Back</button>}
        {isLast
          ? <button onClick={handleFinish}>Submit</button>
          : <button onClick={next}>Next</button>
        }
      </div>
    </div>
  );
}
```

---

## Input Sanitization (XSS Prevention)

```bash
npm install dompurify
npm install --save-dev @types/dompurify
```

```tsx
// lib/sanitize.ts
import DOMPurify from 'dompurify';

// Use when rendering user-generated HTML content
export function sanitizeHtml(dirty: string): string {
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'p', 'br'],
    ALLOWED_ATTR: ['href', 'target'],
  });
}

// ❌ Never do this — XSS vulnerability
<div dangerouslySetInnerHTML={{ __html: userContent }} />

// ✅ Always sanitize first
<div dangerouslySetInnerHTML={{ __html: sanitizeHtml(userContent) }} />

// ✅ Even better — use React's built-in escaping (no dangerouslySetInnerHTML)
<p>{userContent}</p>  // React escapes this automatically
```

```python
# Backend — sanitize on input too
# pip install bleach
import bleach

ALLOWED_TAGS = ['b', 'i', 'em', 'strong', 'a', 'p', 'br']
ALLOWED_ATTRIBUTES = {'a': ['href']}

def sanitize_html(value: str) -> str:
    return bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)

# In Pydantic schema
from pydantic import field_validator

class PostCreate(BaseModel):
    title: str
    body: str

    @field_validator('body')
    @classmethod
    def sanitize_body(cls, v: str) -> str:
        return sanitize_html(v)
```
