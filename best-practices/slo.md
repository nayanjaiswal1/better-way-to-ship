# SLOs & Error Budgets

## Concepts

| Term | Definition |
|------|-----------|
| **SLI** (Service Level Indicator) | Metric you measure — e.g. % of requests < 200ms |
| **SLO** (Service Level Objective) | Target — e.g. 99.9% of requests succeed |
| **Error Budget** | How much failure you can afford — e.g. 43min/month downtime at 99.9% |
| **SLA** | Contract with customers — typically lower than internal SLO |

---

## Define SLOs

```yaml
# slos.yaml — single source of truth, checked into repo
slos:
  api_availability:
    description: "API returns non-5xx responses"
    sli: "1 - (rate(http_requests_total{status=~'5..'}[5m]) / rate(http_requests_total[5m]))"
    target: 99.9       # %
    window: 30d        # rolling window
    error_budget_minutes: 43.2   # 0.1% of 30 days

  api_latency:
    description: "95th percentile latency under 500ms"
    sli: "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
    target: 99.0       # % of time p95 < 500ms
    threshold_ms: 500
    window: 30d
    error_budget_minutes: 432    # 1% of 30 days

  checkout_success:
    description: "Checkout flow completes without error"
    sli: "rate(business_checkout_success_total[5m]) / rate(business_checkout_attempts_total[5m])"
    target: 99.5
    window: 30d

  worker_queue_drain:
    description: "ARQ jobs processed within 5 minutes of enqueue"
    sli: "histogram_quantile(0.99, rate(arq_job_duration_seconds_bucket[5m]))"
    target: 99.0
    threshold_seconds: 300
    window: 30d
```

---

## Prometheus Recording Rules

Pre-compute SLIs — fast dashboards and alerts.

```yaml
# prometheus/slo-rules.yaml
groups:
  - name: slo_recording_rules
    interval: 30s
    rules:
      # API availability — 5m window
      - record: slo:api_availability:ratio_rate5m
        expr: |
          1 - (
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            /
            sum(rate(http_requests_total[5m]))
          )

      # API availability — 1h window (for burn rate)
      - record: slo:api_availability:ratio_rate1h
        expr: |
          1 - (
            sum(rate(http_requests_total{status=~"5.."}[1h]))
            /
            sum(rate(http_requests_total[1h]))
          )

      # API availability — 6h window
      - record: slo:api_availability:ratio_rate6h
        expr: |
          1 - (
            sum(rate(http_requests_total{status=~"5.."}[6h]))
            /
            sum(rate(http_requests_total[6h]))
          )

      # Latency — p95
      - record: slo:api_latency_p95:ratio_rate5m
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          )

      # Error budget remaining — % left this month
      - record: slo:api_availability:error_budget_remaining
        expr: |
          (slo:api_availability:ratio_rate30d - 0.999) / (1 - 0.999)
```

---

## Error Budget Burn Rate Alerts

Burn rate = how fast you're spending the error budget. Alert before budget is exhausted.

```yaml
# prometheus/slo-alerts.yaml
groups:
  - name: slo_alerts
    rules:
      # Fast burn — spending 14x budget (uses 5% budget in 1h → gone in 20h)
      # Page immediately
      - alert: SLOErrorBudgetFastBurn
        expr: |
          (
            (1 - slo:api_availability:ratio_rate1h) > (14 * (1 - 0.999))
            and
            (1 - slo:api_availability:ratio_rate5m) > (14 * (1 - 0.999))
          )
        for: 2m
        labels:
          severity: critical
          slo: api_availability
        annotations:
          summary: "SLO fast burn — {{ $value | humanizePercentage }} error rate"
          description: "Error budget burning 14x faster than sustainable. Page on-call."
          runbook: "https://runbooks.internal/slo-fast-burn"

      # Slow burn — spending 6x budget (uses 10% budget in 6h → exhausted in ~2.5 days)
      # Alert to Slack, not page
      - alert: SLOErrorBudgetSlowBurn
        expr: |
          (
            (1 - slo:api_availability:ratio_rate6h) > (6 * (1 - 0.999))
            and
            (1 - slo:api_availability:ratio_rate1h) > (6 * (1 - 0.999))
          )
        for: 15m
        labels:
          severity: warning
          slo: api_availability
        annotations:
          summary: "SLO slow burn — budget at risk this month"

      # Error budget nearly exhausted
      - alert: SLOErrorBudgetExhausted
        expr: slo:api_availability:error_budget_remaining < 0.10
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Error budget < 10% remaining this month — freeze non-critical deploys"

      # Latency SLO breach
      - alert: SLOLatencyBreach
        expr: slo:api_latency_p95:ratio_rate5m > 0.5
        for: 5m
        labels:
          severity: warning
          slo: api_latency
        annotations:
          summary: "p95 latency {{ $value }}s — SLO threshold 500ms"
```

---

## Grafana Dashboard — SLO Overview

```json
{
  "title": "SLO Dashboard",
  "panels": [
    {
      "title": "API Availability — 30d",
      "type": "stat",
      "targets": [{
        "expr": "slo:api_availability:ratio_rate30d * 100",
        "legendFormat": "Availability %"
      }],
      "thresholds": {
        "steps": [
          { "color": "red",    "value": 0 },
          { "color": "yellow", "value": 99.5 },
          { "color": "green",  "value": 99.9 }
        ]
      }
    },
    {
      "title": "Error Budget Remaining",
      "type": "gauge",
      "targets": [{
        "expr": "slo:api_availability:error_budget_remaining * 100",
        "legendFormat": "Budget Remaining %"
      }],
      "thresholds": {
        "steps": [
          { "color": "red",    "value": 0 },
          { "color": "yellow", "value": 25 },
          { "color": "green",  "value": 50 }
        ]
      }
    },
    {
      "title": "Error Budget Burn Rate",
      "type": "timeseries",
      "targets": [
        {
          "expr": "(1 - slo:api_availability:ratio_rate1h) / (1 - 0.999)",
          "legendFormat": "1h burn rate"
        },
        {
          "expr": "(1 - slo:api_availability:ratio_rate6h) / (1 - 0.999)",
          "legendFormat": "6h burn rate"
        }
      ],
      "thresholds": [
        { "value": 1,  "color": "yellow" },  // burning at budget rate
        { "value": 6,  "color": "orange" },  // slow burn alert
        { "value": 14, "color": "red" }      // fast burn — page
      ]
    }
  ]
}
```

---

## Error Budget Policy

What to do based on budget remaining — written down, agreed by team.

```markdown
# Error Budget Policy

## Budget > 50% remaining
- Full velocity: ship features, run load tests, do migrations
- Postmortems optional for minor incidents

## Budget 25–50% remaining
- Normal velocity: review risk of upcoming deploys
- Postmortems required for all P1 incidents
- Prefer low-risk deploys (feature flags, canary)

## Budget 10–25% remaining
- Slow down: freeze non-critical features
- Every deploy needs explicit approval
- Mandatory reliability work in next sprint

## Budget < 10% remaining
- **Reliability freeze**: only bug fixes and rollbacks
- All engineering focus shifts to reliability
- No new features until budget recovers
- Daily sync with on-call and engineering lead

## Budget exhausted (< 0%)
- Incident declared — follow incident runbook
- Customer communication required
- SRE review before any change to production
```

---

## Instrument Business SLOs

Track user-visible success, not just infra metrics.

```python
# api/v1/checkout.py
from prometheus_client import Counter, Histogram

checkout_attempts = Counter(
    "business_checkout_attempts_total",
    "Checkout attempts",
    ["tenant_id"],
)
checkout_success = Counter(
    "business_checkout_success_total",
    "Successful checkouts",
    ["tenant_id"],
)
checkout_duration = Histogram(
    "business_checkout_duration_seconds",
    "Checkout flow duration",
    buckets=[0.5, 1, 2, 5, 10, 30],
)

@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    tenant_id = str(current_user.tenant_id)
    checkout_attempts.labels(tenant_id=tenant_id).inc()

    with checkout_duration.time():
        try:
            result = await checkout_service.process(body, current_user)
            checkout_success.labels(tenant_id=tenant_id).inc()
            return result
        except Exception:
            # Don't inc success — failure feeds into SLO
            raise
```

---

## SLO Checklist

- [ ] SLOs defined and documented (`slos.yaml`)
- [ ] Error budget policy written and agreed by team
- [ ] Recording rules pre-computing SLIs (fast queries)
- [ ] Multi-window burn rate alerts (1h + 6h for reliability)
- [ ] Error budget exhaustion alert triggers reliability freeze
- [ ] Grafana SLO dashboard with budget gauge visible to whole team
- [ ] Business SLOs tracked (checkout, signup) not just infra
- [ ] Postmortem process tied to error budget consumption
- [ ] SLO targets reviewed quarterly — tighten as system matures
