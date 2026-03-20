# Chaos Engineering

Deliberately inject failures to find weaknesses before production does. Run in staging first, then production during low-traffic windows.

## Principles

```
1. Define steady state   — what does "healthy" look like? (error rate < 0.1%, p95 < 200ms)
2. Hypothesize           — "if pod X dies, traffic shifts to pod Y within 10s"
3. Inject failure        — kill pod, saturate CPU, drop network packets
4. Observe               — did steady state hold? did alerts fire?
5. Fix weaknesses        — if hypothesis failed, fix the gap
6. Run in production     — staging lies; prod is truth (start small)
```

**Never run chaos without:**
- Monitoring dashboards open
- Alert channels active
- Rollback plan ready
- Team aware it's happening

---

## Tools

| Tool | What it does |
|------|-------------|
| **Chaos Mesh** | Kubernetes-native: kill pods, inject network faults, stress CPU/memory |
| **Litmus** | Kubernetes chaos with pre-built experiments library |
| **Toxiproxy** | Inject network latency/failures between services (local + staging) |
| **stress-ng** | CPU, memory, disk stress on Linux nodes |
| **tc (traffic control)** | Linux network packet loss, latency, corruption |

---

## Chaos Mesh — Kubernetes

```bash
# Install
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm install chaos-mesh chaos-mesh/chaos-mesh \
  --namespace chaos-testing \
  --create-namespace \
  --set dashboard.securityMode=false
```

### Kill a Pod

```yaml
# chaos/pod-kill.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: api-pod-kill
  namespace: production
spec:
  action: pod-kill
  mode: one              # kill one pod at a time
  selector:
    namespaces: [production]
    labelSelectors:
      app: api
  scheduler:
    cron: "@every 10m"   # kill one API pod every 10 minutes
```

```bash
# Apply and watch
kubectl apply -f chaos/pod-kill.yaml

# Watch pods recover
kubectl get pods -n production -w

# Expected: killed pod replaced within 30s, traffic unaffected
# Check: error rate in Grafana should stay < 0.1%
```

### Network Latency — Simulate Slow DB

```yaml
# chaos/network-delay.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: db-latency
  namespace: production
spec:
  action: delay
  mode: all
  selector:
    namespaces: [production]
    labelSelectors:
      app: api
  delay:
    latency: "200ms"
    correlation: "25"    # 25% correlation between packets
    jitter: "50ms"
  direction: to
  target:
    selector:
      namespaces: [production]
      labelSelectors:
        app: postgres
    mode: all
  duration: "5m"
```

### Network Partition — Split Brain Test

```yaml
# chaos/network-partition.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: partition-api-from-redis
  namespace: production
spec:
  action: partition
  mode: all
  selector:
    namespaces: [production]
    labelSelectors:
      app: api
  direction: both
  target:
    selector:
      namespaces: [production]
      labelSelectors:
        app: redis
    mode: all
  duration: "2m"
# Expected: API falls back to DB for session validation, error rate spikes but recovers
```

### CPU Stress — Autoscaler Test

```yaml
# chaos/cpu-stress.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: api-cpu-stress
  namespace: production
spec:
  mode: one
  selector:
    namespaces: [production]
    labelSelectors:
      app: api
  stressors:
    cpu:
      workers: 4         # 4 threads burning CPU
      load: 80           # 80% CPU load
  duration: "10m"
# Expected: HPA scales up new pods, p95 latency stays under SLO
```

### Memory Leak Simulation

```yaml
# chaos/memory-stress.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: worker-memory-stress
  namespace: production
spec:
  mode: one
  selector:
    namespaces: [production]
    labelSelectors:
      app: arq-worker
  stressors:
    memory:
      workers: 2
      size: "512MB"      # consume 512MB
  duration: "5m"
# Expected: OOMKilled → pod restarts → Celery/ARQ resumes, no job loss
```

---

## Toxiproxy — Network Faults Between Services

Perfect for local dev and staging — no Kubernetes required.

```bash
pip install toxiproxy-python
# or
docker run -p 8474:8474 -p 5432:5432 ghcr.io/shopify/toxiproxy
```

```python
# tests/chaos/test_db_resilience.py
import toxiproxy
import pytest
import time

@pytest.fixture
def proxy():
    client = toxiproxy.Toxiproxy()
    proxy  = client.create("postgres_proxy", listen="0.0.0.0:15432", upstream="postgres:5432")
    yield proxy
    proxy.destroy()

def test_app_handles_slow_db(proxy, api_client, auth_headers):
    """App should return 503 (not hang) when DB is slow."""
    # Inject 3s latency on all DB connections
    proxy.add_toxic("latency", type="latency", attributes={"latency": 3000})

    start    = time.time()
    response = api_client.get("/api/v1/users/", headers=auth_headers, timeout=5)
    elapsed  = time.time() - start

    # Should fail fast with 503, not hang for 3s
    assert response.status_code == 503
    assert elapsed < 1.5   # circuit breaker / timeout fired

    proxy.remove_toxic("latency")

def test_app_handles_db_connection_loss(proxy, api_client, auth_headers):
    """App should return cached data or 503 when DB is down."""
    proxy.add_toxic("down", type="timeout", attributes={"timeout": 0})

    response = api_client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "error"

    proxy.remove_toxic("down")

def test_celery_retries_on_redis_failure(proxy):
    """Tasks should retry when Redis is temporarily unavailable."""
    # Cut Redis for 5 seconds
    proxy.add_toxic("redis_down", type="timeout", attributes={"timeout": 0})
    time.sleep(5)
    proxy.remove_toxic("redis_down")

    # Tasks that were queued before the outage should retry and complete
    result = send_test_task.delay()
    assert result.get(timeout=30) == "ok"
```

---

## Game Days — Structured Chaos Sessions

Quarterly exercises where the team deliberately breaks things.

```markdown
# Game Day Template — Q1 2026

## Scenario: Primary DB Failover
**Hypothesis**: Promoting the read replica takes < 5 min, error rate < 1% during failover.
**Method**: `aws rds failover-db-cluster --db-cluster-identifier prod-myapp`
**Observe**: Grafana error rate, p95 latency, customer-visible errors
**Result**: ✅ Failover completed in 3m 20s. Error rate spiked to 0.4% during failover.
**Action**: Reduce connection timeout from 30s to 5s to fail faster.

---

## Scenario: Celery Workers Wiped
**Hypothesis**: If all workers die, queued tasks process within 10 min of recovery.
**Method**: `kubectl delete deployment celery-worker -n production`
**Observe**: Queue depth (KEDA metric), task completion rate
**Result**: ❌ KEDA took 8 min to spin up new workers (cold start). Queue depth hit 4,200.
**Action**: Set `minReplicaCount: 1` (never fully scale to zero for critical workers).

---

## Scenario: Redis Eviction Under Memory Pressure
**Hypothesis**: If Redis evicts cache keys, app falls back to DB without errors.
**Method**: `redis-cli CONFIG SET maxmemory 10mb` (force eviction)
**Observe**: Cache hit rate, DB query rate, error rate
**Result**: ✅ Cache miss rate spiked to 95%, DB handled load, no user-visible errors.
**Action**: None — graceful degradation confirmed.
```

---

## Chaos Experiments Runbook

```markdown
## Before Every Experiment

- [ ] Grafana dashboards open (error rate, p95, pod count)
- [ ] Alert Slack channel monitored
- [ ] Team notified in #engineering: "Starting chaos experiment: [name]"
- [ ] Rollback command ready to paste
- [ ] Start time noted for incident timeline

## During

- Watch error rate — abort if > 1% for > 2 min (our SLO burn rate)
- Watch p95 — abort if > 2s sustained
- Note timestamps of all observations

## After

- Remove chaos injection
- Verify system returns to steady state (< 5 min)
- Write up findings: what held, what broke, action items
- File tickets for any gaps found
- Update this runbook with results

## Abort Command
kubectl delete podchaos,networkchaos,stresschaos --all -n production
```

---

## CI — Automated Chaos Tests (Staging)

```yaml
# .github/workflows/chaos.yml
name: Chaos Tests

on:
  schedule:
    - cron: '0 2 * * 2'   # Tuesday 2am — low traffic on staging

jobs:
  chaos:
    runs-on: ubuntu-latest
    environment: staging

    steps:
      - uses: actions/checkout@v4

      - name: Install Chaos Mesh CLI
        run: |
          curl -sSL https://mirrors.chaos-mesh.org/v2.6.0/install.sh | bash -s -- --local kind

      - name: Run pod kill test
        run: |
          kubectl apply -f chaos/tests/pod-kill.yaml
          sleep 60
          # Assert: error rate stayed below 0.1%
          python scripts/assert_slo.py --metric error_rate --threshold 0.001 --window 60s

      - name: Run DB latency test
        run: |
          kubectl apply -f chaos/tests/db-latency-100ms.yaml
          sleep 120
          python scripts/assert_slo.py --metric p95_latency_ms --threshold 500 --window 120s

      - name: Cleanup
        if: always()
        run: kubectl delete podchaos,networkchaos --all -n staging
```

```python
# scripts/assert_slo.py — query Prometheus, fail CI if SLO breached
import sys
import requests

def check_metric(metric: str, threshold: float, window: str):
    queries = {
        "error_rate":     f'rate(http_requests_total{{status=~"5.."}}[{window}]) / rate(http_requests_total[{window}])',
        "p95_latency_ms": f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[{window}])) * 1000',
    }
    query = queries[metric]
    res   = requests.get("http://prometheus:9090/api/v1/query", params={"query": query})
    value = float(res.json()["data"]["result"][0]["value"][1])

    print(f"{metric}: {value:.4f} (threshold: {threshold})")
    if value > threshold:
        print(f"❌ SLO BREACH: {metric} {value:.4f} > {threshold}")
        sys.exit(1)
    print(f"✅ SLO held")
```

---

## Chaos Engineering Checklist

### Before Starting
- [ ] Steady state defined (error rate, latency, queue depth)
- [ ] Monitoring dashboards open before injecting
- [ ] Rollback command documented and tested
- [ ] Team notified — no surprise chaos

### Experiments to Run (Quarterly)
- [ ] Pod kill — single API pod dies, traffic redistributes
- [ ] All pods killed — deployment recovers from zero
- [ ] DB failover — replica promoted, app reconnects
- [ ] Redis down — cache miss, app falls back to DB
- [ ] Network partition API ↔ DB — circuit breaker fires, 503 returned
- [ ] Network latency 200ms — p95 stays under SLO
- [ ] CPU stress — HPA scales, p95 recovers
- [ ] Worker pods killed — KEDA respawns, queued tasks complete
- [ ] TURN server down — WebRTC falls back to STUN-only

### After Each Experiment
- [ ] System returned to steady state within 5 min
- [ ] Alerts fired when they should have
- [ ] No alerts fired when they shouldn't have (false positives)
- [ ] Findings documented — action items filed
- [ ] Runbook updated with results
