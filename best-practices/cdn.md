# CDN & Asset Optimization

## CloudFront Setup

```hcl
# terraform/modules/cdn/main.tf
resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  aliases             = ["app.example.com", "cdn.example.com"]

  # React SPA — served from S3
  origin {
    domain_name            = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id              = "frontend-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.main.id
  }

  # API — passthrough to ALB
  origin {
    domain_name = aws_lb.api.dns_name
    origin_id   = "api-alb"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Static uploads — served from S3
  origin {
    domain_name            = aws_s3_bucket.uploads.bucket_regional_domain_name
    origin_id              = "uploads-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.main.id
  }

  # Default: serve React app from S3
  default_cache_behavior {
    target_origin_id       = "frontend-s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    # Hashed assets (bundle.abc123.js) — cache forever
    min_ttl     = 0
    default_ttl = 86400      # 1 day for index.html
    max_ttl     = 31536000   # 1 year
  }

  # API — no caching, pass through
  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "api-alb"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Origin", "Accept", "Cookie"]
      cookies { forward = "all" }
    }

    min_ttl     = 0
    default_ttl = 0     # no caching for API
    max_ttl     = 0
  }

  # User uploads — long cache
  ordered_cache_behavior {
    path_pattern           = "/uploads/*"
    target_origin_id       = "uploads-s3"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 604800   # 7 days
    max_ttl     = 31536000 # 1 year
  }

  # SPA routing — 404 → index.html (React Router handles it)
  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.main.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  price_class = "PriceClass_100"   # US + Europe only — cheapest
}

resource "aws_cloudfront_origin_access_control" "main" {
  name                              = "myapp-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}
```

---

## Cache Headers — Frontend Build

```ts
// vite.config.ts — content-hash all assets (cache-bust automatically)
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        // [hash] in filename = safe to cache forever
        entryFileNames: 'assets/[name].[hash].js',
        chunkFileNames: 'assets/[name].[hash].js',
        assetFileNames: 'assets/[name].[hash][extname]',
      },
    },
  },
});
```

```python
# FastAPI / Django — correct cache headers per file type

# index.html — NEVER cache (contains hashed asset references)
# Cache-Control: no-cache, no-store, must-revalidate

# /assets/main.abc123.js — cache forever (hash changes on every build)
# Cache-Control: public, max-age=31536000, immutable
```

```nginx
# nginx serving static files directly (non-CloudFront)
location /assets/ {
    root /var/www/html;
    expires 1y;
    add_header Cache-Control "public, max-age=31536000, immutable";
    gzip_static on;    # serve pre-compressed .gz files
}

location = /index.html {
    root /var/www/html;
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    add_header Pragma "no-cache";
    expires 0;
}
```

---

## S3 Static Hosting + CloudFront Invalidation

```bash
# deploy/deploy_frontend.sh
#!/bin/bash
set -euo pipefail

BUCKET="myapp-frontend-prod"
DISTRIBUTION_ID="E1234567890"
BUILD_DIR="dist"

# Build
npm run build

# Upload hashed assets — cache forever
aws s3 sync "$BUILD_DIR/assets" "s3://$BUCKET/assets" \
  --cache-control "public, max-age=31536000, immutable" \
  --delete

# Upload index.html — no cache
aws s3 cp "$BUILD_DIR/index.html" "s3://$BUCKET/index.html" \
  --cache-control "no-cache, no-store, must-revalidate"

# Invalidate only index.html — assets are cache-busted by hash
aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/index.html"

echo "Deployed. CloudFront serving new index.html."
```

---

## Image CDN — Serve Optimized Images

Never serve raw uploaded images. Resize + convert to WebP at the edge.

### Option A: CloudFront + Lambda@Edge

```python
# lambda/image_transform/index.py — runs at CloudFront edge
import boto3
from PIL import Image
import io

def handler(event, context):
    request = event["Records"][0]["cf"]["request"]
    uri     = request["uri"]          # /uploads/user/avatar.jpg
    params  = request.get("querystring", "")  # ?w=200&h=200&fmt=webp

    if not params:
        return request   # no transform needed

    # Parse params
    w   = int(get_param(params, "w", 0))
    h   = int(get_param(params, "h", 0))
    fmt = get_param(params, "fmt", "auto")

    # Fetch original from S3
    s3  = boto3.client("s3")
    obj = s3.get_object(Bucket="myapp-uploads", Key=uri.lstrip("/"))
    img = Image.open(io.BytesIO(obj["Body"].read()))

    # Resize preserving aspect ratio
    if w or h:
        img.thumbnail((w or img.width, h or img.height), Image.LANCZOS)

    # Convert format
    if fmt == "webp" or (fmt == "auto" and "webp" in event["Records"][0]["cf"]["request"].get("headers", {}).get("accept", [{}])[0].get("value", "")):
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=85)
        content_type = "image/webp"
    else:
        buf = io.BytesIO()
        img.save(buf, img.format or "JPEG", quality=85)
        content_type = f"image/{(img.format or 'jpeg').lower()}"

    return {
        "status": "200",
        "headers": {
            "content-type": [{"key": "Content-Type", "value": content_type}],
            "cache-control": [{"key": "Cache-Control", "value": "public, max-age=604800"}],
        },
        "body": buf.getvalue(),
        "bodyEncoding": "base64",
    }
```

### Option B: imgproxy (Self-Hosted, Simpler)

```yaml
# docker-compose.yml
imgproxy:
  image: darthsim/imgproxy:latest
  environment:
    IMGPROXY_KEY:  ${IMGPROXY_KEY}     # random hex secret
    IMGPROXY_SALT: ${IMGPROXY_SALT}
    IMGPROXY_MAX_SRC_RESOLUTION: 25    # megapixels
    IMGPROXY_QUALITY: 85
    IMGPROXY_WEBP_COMPRESSION: 85
    IMGPROXY_USE_S3: "true"
    AWS_ACCESS_KEY_ID:     ${AWS_ACCESS_KEY_ID}
    AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}
    AWS_REGION: us-east-1
  ports:
    - "8080:8080"
```

```python
# common/images.py — generate signed imgproxy URLs
import hashlib, hmac, base64

def imgproxy_url(
    s3_key: str,
    width: int = 0,
    height: int = 0,
    resizing_type: str = "fill",
    format: str = "webp",
) -> str:
    key  = bytes.fromhex(settings.IMGPROXY_KEY)
    salt = bytes.fromhex(settings.IMGPROXY_SALT)

    path = f"/{resizing_type}/{width}/{height}/ce/0/plain/s3://myapp-uploads/{s3_key}@{format}"
    signature = base64.urlsafe_b64encode(
        hmac.new(key, salt + path.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()

    return f"https://images.example.com/{signature}{path}"
```

```tsx
// React — responsive images with WebP + fallback
function Avatar({ user }: { user: User }) {
  const src    = imgproxyUrl(user.avatar_key, 64, 64);
  const src2x  = imgproxyUrl(user.avatar_key, 128, 128);

  return (
    <picture>
      <source srcSet={`${src} 1x, ${src2x} 2x`} type="image/webp" />
      <img src={src} alt={user.name} width={64} height={64} loading="lazy" />
    </picture>
  );
}
```

---

## Cloudflare (Alternative to CloudFront)

```hcl
# terraform/cloudflare.tf
resource "cloudflare_zone_settings_override" "main" {
  zone_id = var.cloudflare_zone_id

  settings {
    ssl            = "full_strict"
    min_tls_version = "1.2"
    tls_1_3        = "on"
    http3          = "on"
    brotli         = "on"
    minify {
      js   = "on"
      css  = "on"
      html = "off"   # don't minify — can break React hydration
    }
  }
}

# Cache rules
resource "cloudflare_ruleset" "cache" {
  zone_id = var.cloudflare_zone_id
  name    = "Cache Rules"
  kind    = "zone"
  phase   = "http_response_headers_transform"

  rules {
    action = "rewrite"
    action_parameters {
      headers {
        name      = "Cache-Control"
        operation = "set"
        value     = "public, max-age=31536000, immutable"
      }
    }
    expression = "(http.request.uri.path matches \"^/assets/\")"
    enabled    = true
  }
}

# Always use HTTPS
resource "cloudflare_ruleset" "redirect_http" {
  zone_id = var.cloudflare_zone_id
  phase   = "http_request_redirect"
  kind    = "zone"
  name    = "Redirect HTTP to HTTPS"

  rules {
    action = "redirect"
    action_parameters {
      from_value {
        status_code = 301
        target_url { value = "https://{http.request.full_uri}" }
      }
    }
    expression = "(http.request.scheme eq \"http\")"
    enabled    = true
  }
}
```

---

## Cache Invalidation Strategy

```python
# When to invalidate CloudFront cache:
# 1. New frontend deploy → invalidate /index.html (only)
# 2. User uploads new avatar → invalidate specific path
# 3. Admin updates a public page → targeted invalidation

# services/cdn.py
import boto3

cf = boto3.client("cloudfront")

def invalidate(paths: list[str]) -> None:
    """Invalidate specific CloudFront paths."""
    import time
    cf.create_invalidation(
        DistributionId=settings.CLOUDFRONT_DISTRIBUTION_ID,
        InvalidationBatch={
            "Paths": {"Quantity": len(paths), "Items": paths},
            "CallerReference": str(int(time.time())),
        },
    )

# Examples
invalidate(["/index.html"])                      # new deploy
invalidate([f"/uploads/{user.public_id}/avatar*"])  # user changed avatar
invalidate(["/*"])                               # nuclear — avoid, costs money
```

---

## Performance Budget — CI Enforcement

```ts
// vite.config.ts
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor:  ["react", "react-dom"],
          router:  ["react-router-dom"],
          query:   ["@tanstack/react-query"],
          ui:      ["@radix-ui/react-dialog", "@radix-ui/react-dropdown-menu"],
        },
      },
    },
  },
});
```

```yaml
# .github/workflows/ci.yml — fail if bundle too large
- name: Build frontend
  run: npm run build

- name: Check bundle size
  run: |
    MAIN_SIZE=$(stat -c%s dist/assets/main.*.js 2>/dev/null || echo 0)
    VENDOR_SIZE=$(stat -c%s dist/assets/vendor.*.js 2>/dev/null || echo 0)
    LIMIT=250000   # 250KB

    echo "main.js: $(($MAIN_SIZE / 1024))KB"
    echo "vendor.js: $(($VENDOR_SIZE / 1024))KB"

    if [ "$MAIN_SIZE" -gt "$LIMIT" ]; then
      echo "❌ main.js exceeds 250KB budget"
      exit 1
    fi
```

---

## CDN Checklist

- [ ] CloudFront in front of S3 (frontend) and ALB (API) — never expose S3 directly
- [ ] Hashed asset filenames (`[hash]` in Vite config) — safe to cache forever
- [ ] `index.html` served with `no-cache` — always fetches latest
- [ ] API path (`/api/*`) bypasses CloudFront cache — `max-age=0`
- [ ] CloudFront invalidation in deploy script — only `/index.html`
- [ ] Image CDN (imgproxy or Lambda@Edge) — never serve raw uploaded images
- [ ] WebP conversion at edge — smaller files, same quality
- [ ] TLS 1.2+ minimum — configured in CloudFront viewer certificate
- [ ] `compress = true` in CloudFront — gzip/brotli enabled
- [ ] Bundle size budget enforced in CI
- [ ] `PriceClass_100` — US + Europe only unless you need global
