# File Processing

## PDF Generation

### WeasyPrint — HTML → PDF (Django / FastAPI)

```bash
pip install weasyprint
```

```python
# services/pdf.py
from weasyprint import HTML, CSS
from django.template.loader import render_to_string   # Django
# from jinja2 import Environment, FileSystemLoader    # FastAPI

def generate_invoice_pdf(invoice) -> bytes:
    """Render HTML template → PDF bytes."""
    html_str = render_to_string("pdfs/invoice.html", {
        "invoice": invoice,
        "tenant":  invoice.tenant,
        "items":   invoice.items.all(),
    })
    return HTML(string=html_str, base_url="https://app.example.com").write_pdf()
```

```html
<!-- templates/pdfs/invoice.html -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {
      size: A4;
      margin: 20mm 15mm;
      @bottom-right {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9pt;
        color: #9ca3af;
      }
    }
    body { font-family: 'Helvetica Neue', sans-serif; font-size: 10pt; color: #111827; }
    .header { display: flex; justify-content: space-between; margin-bottom: 24pt; }
    table  { width: 100%; border-collapse: collapse; margin-top: 16pt; }
    th, td { padding: 8pt; text-align: left; border-bottom: 1px solid #e5e7eb; }
    th     { background: #f9fafb; font-weight: 600; }
    .total { font-size: 12pt; font-weight: 700; text-align: right; margin-top: 16pt; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <strong>{{ tenant.name }}</strong><br>
      {{ tenant.address }}
    </div>
    <div>
      <h1 style="margin:0; font-size:18pt;">Invoice</h1>
      <div>#{{ invoice.number }}</div>
      <div>{{ invoice.date|date:"F j, Y" }}</div>
    </div>
  </div>

  <table>
    <thead>
      <tr><th>Description</th><th>Qty</th><th>Unit Price</th><th>Total</th></tr>
    </thead>
    <tbody>
      {% for item in items %}
      <tr>
        <td>{{ item.description }}</td>
        <td>{{ item.quantity }}</td>
        <td>${{ item.unit_price }}</td>
        <td>${{ item.total }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="total">Total: ${{ invoice.total }}</div>
</body>
</html>
```

```python
# Serve PDF via API
# Django
class InvoicePDFView(APIView):
    def get(self, request, public_id):
        invoice = get_object_or_404(Invoice, public_id=public_id, tenant=request.user.tenant)
        pdf = generate_invoice_pdf(invoice)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="invoice-{invoice.number}.pdf"'
        return response

# FastAPI
@router.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str, current_user: User = Depends(get_current_user)):
    invoice = await invoice_repo.get_by_public_id(invoice_id, current_user.tenant_id)
    pdf = generate_invoice_pdf(invoice)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice-{invoice.number}.pdf"'},
    )
```

### Generate PDF Async via Celery (for large reports)

```python
# apps/reports/tasks.py
from celery import shared_task

@shared_task
def generate_report_pdf(report_id: int, user_id: int) -> str:
    from apps.reports.models import Report
    from apps.users.models import User
    from services.pdf import generate_report_pdf as _generate
    from services.storage import upload_to_s3

    report = Report.all_objects.get(id=report_id)
    pdf = _generate(report)

    # Upload to S3, return download URL
    key = f"reports/{report.public_id}/report.pdf"
    upload_to_s3(pdf, key, content_type="application/pdf")

    # Notify user via SSE/WebSocket
    from apps.notifications.services import NotificationService
    user = User.objects.get(id=user_id)
    NotificationService.create(
        user=user,
        type="report.ready",
        title="Your report is ready",
        data={"download_key": key},
    )
    return key
```

---

## Image Processing — Pillow

```bash
pip install Pillow
```

```python
# services/images.py
from PIL import Image, ImageOps
import io
from typing import Literal

ImageFormat = Literal["JPEG", "PNG", "WEBP"]

def resize_image(
    data: bytes,
    width: int,
    height: int,
    fit: Literal["cover", "contain", "fill"] = "cover",
    format: ImageFormat = "WEBP",
    quality: int = 85,
) -> bytes:
    """Resize + convert image. Returns bytes."""
    img = Image.open(io.BytesIO(data))

    # Convert to RGB — WEBP doesn't support CMYK or palette modes
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    if fit == "cover":
        img = ImageOps.fit(img, (width, height), Image.LANCZOS)
    elif fit == "contain":
        img.thumbnail((width, height), Image.LANCZOS)
    elif fit == "fill":
        img = img.resize((width, height), Image.LANCZOS)

    out = io.BytesIO()
    save_kwargs = {"quality": quality, "optimize": True}
    if format == "JPEG":
        img = img.convert("RGB")  # remove alpha for JPEG
    img.save(out, format=format, **save_kwargs)
    return out.getvalue()

def generate_avatar_variants(data: bytes) -> dict[str, bytes]:
    """Generate multiple sizes for an avatar upload."""
    return {
        "32":  resize_image(data, 32,  32,  format="WEBP"),
        "64":  resize_image(data, 64,  64,  format="WEBP"),
        "128": resize_image(data, 128, 128, format="WEBP"),
        "256": resize_image(data, 256, 256, format="WEBP"),
    }

def validate_image(data: bytes, max_mb: int = 10) -> None:
    """Validate before processing — reject invalid files."""
    if len(data) > max_mb * 1024 * 1024:
        raise ValueError(f"Image exceeds {max_mb}MB limit")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # raises on corrupt/invalid files
    except Exception:
        raise ValueError("Invalid or corrupt image file")
```

```python
# apps/users/tasks.py — process avatar upload in background
from celery import shared_task

@shared_task
def process_avatar_upload(user_id: int, s3_key: str) -> None:
    import boto3
    from services.images import validate_image, generate_avatar_variants

    s3 = boto3.client("s3")

    # Download original
    obj  = s3.get_object(Bucket=settings.S3_BUCKET, Key=s3_key)
    data = obj["Body"].read()

    validate_image(data)

    # Generate variants and upload
    variants = generate_avatar_variants(data)
    for size, img_bytes in variants.items():
        s3.put_object(
            Bucket=settings.S3_BUCKET,
            Key=f"avatars/{user_id}/{size}.webp",
            Body=img_bytes,
            ContentType="image/webp",
            CacheControl="public, max-age=31536000",
        )

    # Update user record
    from apps.users.models import User
    User.objects.filter(id=user_id).update(
        avatar_key=f"avatars/{user_id}",
    )

    # Delete the raw original — only keep processed variants
    s3.delete_object(Bucket=settings.S3_BUCKET, Key=s3_key)
```

---

## Virus Scanning — ClamAV

Never store or process uploaded files without scanning.

```bash
pip install clamd
docker run -d --name clamav -p 3310:3310 clamav/clamav
```

```python
# services/antivirus.py
import clamd
from django.conf import settings

def scan_file(data: bytes, filename: str) -> None:
    """Scan file for viruses. Raises on infection."""
    try:
        cd = clamd.ClamdNetworkSocket(
            host=settings.CLAMAV_HOST,
            port=settings.CLAMAV_PORT,
            timeout=30,
        )
        result = cd.instream(io.BytesIO(data))
        status, description = result["stream"]

        if status == "FOUND":
            raise ValueError(f"Malware detected in {filename}: {description}")
    except clamd.ConnectionError:
        # ClamAV unavailable — log warning but don't block upload
        # Replace with hard fail if compliance requires it
        logger.warning("ClamAV unavailable — skipping scan", filename=filename)
```

```python
# apps/uploads/views.py — scan before processing
class FileUploadView(APIView):
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response(status=400)

        data = file.read()

        # 1. Validate size + type
        if file.size > 50 * 1024 * 1024:
            raise AppValidationError("File exceeds 50MB limit")

        allowed_types = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
        if file.content_type not in allowed_types:
            raise AppValidationError(f"File type {file.content_type} not allowed")

        # 2. Virus scan
        scan_file(data, file.name)

        # 3. Upload to S3 (quarantine folder — not public)
        key = f"quarantine/{request.user.public_id}/{uuid4()}/{file.name}"
        upload_to_s3(data, key)

        # 4. Process async (resize images, extract text from PDFs, etc.)
        process_upload.delay(key, request.user.id, file.content_type)

        return Response({"status": "processing", "key": key}, status=202)
```

---

## File Type Validation — Magic Bytes

Never trust the file extension or Content-Type header — check magic bytes.

```bash
pip install python-magic
```

```python
# services/files.py
import magic

ALLOWED_MIME_TYPES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png":  [".png"],
    "image/webp": [".webp"],
    "application/pdf": [".pdf"],
    "text/csv":   [".csv"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
}

def validate_file_type(data: bytes, claimed_content_type: str) -> str:
    """Detect real MIME type from magic bytes — ignore claimed type."""
    real_type = magic.from_buffer(data, mime=True)

    if real_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"File type {real_type} is not allowed")

    if real_type != claimed_content_type:
        raise ValueError(f"File content ({real_type}) does not match declared type ({claimed_content_type})")

    return real_type
```

---

## Safe Filename Handling

```python
# common/validators.py
import re
from pathlib import Path

def safe_filename(filename: str) -> str:
    """
    Strip path components and dangerous characters.
    Returns a safe filename suitable for storage.
    """
    # Get just the filename, no path
    name = Path(filename).name

    # Remove everything except alphanumeric, dash, underscore, dot
    name = re.sub(r"[^\w\-.]", "_", name)

    # Collapse multiple dots (prevent double extensions like file.php.jpg)
    name = re.sub(r"\.{2,}", ".", name)

    # Limit length
    if len(name) > 255:
        stem, ext = Path(name).stem[:240], Path(name).suffix
        name = stem + ext

    return name or "file"
```

---

## Excel Processing — openpyxl

```bash
pip install openpyxl
```

```python
# services/excel.py
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
import io

def generate_orders_excel(orders: list) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Orders"

    # Styled header
    headers = ["Reference", "Customer", "Amount", "Status", "Date"]
    header_fill = PatternFill(start_color="3B82F6", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, order in enumerate(orders, 2):
        ws.cell(row=row_idx, column=1, value=order.reference)
        ws.cell(row=row_idx, column=2, value=order.customer_name)
        ws.cell(row=row_idx, column=3, value=float(order.amount))
        ws.cell(row=row_idx, column=4, value=order.status)
        ws.cell(row=row_idx, column=5, value=order.created_at.strftime("%Y-%m-%d"))

    # Auto-fit column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 50)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

def parse_import_excel(data: bytes) -> list[dict]:
    """Parse uploaded Excel file → list of dicts."""
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Empty spreadsheet")

    headers = [str(h).lower().strip() for h in rows[0]]
    return [dict(zip(headers, row)) for row in rows[1:] if any(row)]
```

---

## File Processing Checklist

- [ ] File size limit enforced before reading content (not after)
- [ ] MIME type validated from magic bytes — not from extension or Content-Type
- [ ] Filename sanitized — no path traversal, no double extensions
- [ ] Virus scan (ClamAV) before storing or processing
- [ ] Raw uploads stored in `quarantine/` prefix — not publicly accessible
- [ ] Image processing (resize, convert to WebP) done in Celery task — not in request
- [ ] Raw originals deleted after variants generated
- [ ] PDF generation with WeasyPrint for styled documents
- [ ] Excel import validates header row before processing data
- [ ] Large report PDFs generated async — user notified when ready
