# Cost Optimization

## Compute — EC2 / EKS

### Spot Instances for Workers

Workers are stateless and retryable — perfect for spot (70-90% cheaper).

```hcl
# terraform/modules/eks/main.tf
resource "aws_eks_node_group" "workers" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "workers-spot"
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = var.private_subnet_ids

  capacity_type = "SPOT"   # 70-90% cheaper than ON_DEMAND

  # Multiple instance types = higher spot availability
  instance_types = ["m5.xlarge", "m5a.xlarge", "m4.xlarge", "m5d.xlarge"]

  scaling_config {
    min_size     = 0
    max_size     = 20
    desired_size = 2
  }

  # Spot interruption handling — drain before termination
  labels = { "node-type" = "spot-worker" }
  taint {
    key    = "spot"
    value  = "true"
    effect = "NO_SCHEDULE"
  }
}

# On-demand for API — can't afford interruption
resource "aws_eks_node_group" "api" {
  cluster_name  = aws_eks_cluster.main.name
  capacity_type = "ON_DEMAND"
  instance_types = ["m5.large"]

  scaling_config {
    min_size     = 2
    max_size     = 20
    desired_size = 3
  }
}
```

```yaml
# k8s/arq-worker-deployment.yaml — tolerate spot taint
spec:
  tolerations:
    - key: "spot"
      operator: "Equal"
      value: "true"
      effect: "NoSchedule"
  nodeSelector:
    node-type: spot-worker

  # Graceful shutdown on spot interruption
  terminationGracePeriodSeconds: 30
  containers:
    - name: worker
      lifecycle:
        preStop:
          exec:
            command: ["arq", "--drain"]  # finish current job, stop taking new ones
```

### Right-Sizing — Never Over-Provision

```bash
# Use VPA (Vertical Pod Autoscaler) in recommendation mode
kubectl apply -f https://github.com/kubernetes/autoscaler/releases/latest/download/vertical-pod-autoscaler.yaml

# Check recommendations — update resource requests/limits accordingly
kubectl describe vpa api -n production
# Output: recommended cpu: 180m, memory: 400Mi (vs your request of 250m/256Mi)
```

---

## Database — RDS

### Reserved Instances

```bash
# Check current RDS usage first
aws ce get-cost-and-usage \
  --time-period Start=2026-02-01,End=2026-03-01 \
  --granularity MONTHLY \
  --filter '{"Dimensions":{"Key":"SERVICE","Values":["Amazon Relational Database Service"]}}' \
  --metrics BlendedCost

# Purchase 1-year reserved instance (40% savings vs on-demand)
# Do this only after 3+ months of stable sizing
aws rds purchase-reserved-db-instances-offering \
  --reserved-db-instances-offering-id <offering-id> \
  --reserved-db-instance-id prod-myapp-db-reserved
```

### Connection Pooling Saves Money

PgBouncer pools connections → smaller DB instance needed.

```ini
# pgbouncer.ini — 10 app pods × 10 connections = 100 connections to PgBouncer
# PgBouncer holds only 20 connections to RDS
# → Can use db.t3.medium instead of db.r6g.large = 60% cost saving

[databases]
myapp = host=prod-myapp-db.rds.amazonaws.com port=5432 dbname=myapp

[pgbouncer]
pool_mode = transaction
max_client_conn = 200
default_pool_size = 20   # connections to actual DB
```

### Aurora Serverless v2 — Pay Per ACU

```hcl
# For variable/unpredictable workloads
resource "aws_rds_cluster" "main" {
  engine         = "aurora-postgresql"
  engine_version = "15.4"
  engine_mode    = "provisioned"  # required for Serverless v2

  serverlessv2_scaling_configuration {
    min_capacity = 0.5   # minimum 0.5 ACUs (~$0.12/hr)
    max_capacity = 16    # scale up to 16 ACUs under load
  }
}

resource "aws_rds_cluster_instance" "main" {
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.serverless"  # uses Serverless v2
  engine             = aws_rds_cluster.main.engine
}
```

---

## Storage — S3

### Intelligent Tiering — Automatic Cost Reduction

```hcl
# Automatically moves objects to cheaper storage tiers based on access patterns
resource "aws_s3_bucket_intelligent_tiering_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  name   = "entire-bucket"

  tiering {
    access_tier = "DEEP_ARCHIVE_ACCESS"
    days        = 180   # objects not accessed in 180 days → Glacier Deep Archive
  }
  tiering {
    access_tier = "ARCHIVE_ACCESS"
    days        = 90    # not accessed in 90 days → Glacier
  }
}
```

### Lifecycle Rules — Delete What You Don't Need

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    id     = "delete-temp-uploads"
    status = "Enabled"

    filter { prefix = "temp/" }

    expiration {
      days = 1  # delete temp files after 1 day
    }
  }

  rule {
    id     = "archive-old-exports"
    status = "Enabled"

    filter { prefix = "exports/" }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"  # 40% cheaper, for infrequent access
    }

    transition {
      days          = 90
      storage_class = "GLACIER"      # 80% cheaper
    }

    expiration {
      days = 365  # delete after 1 year
    }
  }

  rule {
    id     = "clean-old-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 30  # delete old versions after 30 days
    }
  }
}
```

---

## Cache — ElastiCache

### Cache Hit Rate Monitoring

Low cache hit rate = paying for DB queries you shouldn't need.

```python
# middleware/cache_metrics.py
from prometheus_client import Counter

cache_hits   = Counter("cache_hits_total",   "Cache hits",   ["cache_key_prefix"])
cache_misses = Counter("cache_misses_total", "Cache misses", ["cache_key_prefix"])

class InstrumentedCache:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def get(self, key: str, prefix: str = "default"):
        value = await self.redis.get(key)
        if value is not None:
            cache_hits.labels(cache_key_prefix=prefix).inc()
        else:
            cache_misses.labels(cache_key_prefix=prefix).inc()
        return value
```

```yaml
# Alert when hit rate drops (expensive — DB getting hammered)
- alert: LowCacheHitRate
  expr: |
    rate(cache_hits_total[5m])
    /
    (rate(cache_hits_total[5m]) + rate(cache_misses_total[5m]))
    < 0.7
  for: 10m
  annotations:
    summary: "Cache hit rate {{ $value | humanizePercentage }} — review TTLs"
```

---

## Network — Data Transfer Costs

Data transfer is often the hidden cost.

```python
# ✅ Compress API responses — especially for large lists
# FastAPI + GZip middleware
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)  # compress responses > 1KB
```

```hcl
# Keep traffic in the same region/AZ
# RDS, ElastiCache, EKS in same AZ = zero cross-AZ transfer cost

resource "aws_elasticache_replication_group" "main" {
  preferred_cache_cluster_azs = ["us-east-1a"]  # same AZ as EKS nodes
}

resource "aws_db_subnet_group" "main" {
  subnet_ids = [
    var.subnet_us_east_1a,  # primary — same AZ as compute
    var.subnet_us_east_1b,  # standby
  ]
}
```

```python
# ✅ Field selection — don't send data the client doesn't need
# GET /api/v1/users?fields=id,name,email
# See api-patterns.md for full implementation

# ✅ Pagination — never return unbounded lists
# Always default page_size=20, max=100
```

---

## Cost Monitoring

### AWS Cost Anomaly Detection

```hcl
resource "aws_ce_anomaly_monitor" "main" {
  name         = "myapp-cost-monitor"
  monitor_type = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "main" {
  name      = "myapp-cost-alerts"
  frequency = "DAILY"

  monitor_arn_list = [aws_ce_anomaly_monitor.main.arn]

  subscriber {
    address = "oncall@example.com"
    type    = "EMAIL"
  }

  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      values        = ["50"]  # alert if spend anomaly > $50/day
      match_options = ["GREATER_THAN_OR_EQUAL"]
    }
  }
}
```

### Monthly Budget Alerts

```hcl
resource "aws_budgets_budget" "monthly" {
  name         = "myapp-monthly-budget"
  budget_type  = "COST"
  limit_amount = "3000"   # $3000/month
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator = "GREATER_THAN"
    threshold           = 80   # alert at 80% of budget
    threshold_type      = "PERCENTAGE"
    notification_type   = "ACTUAL"
    subscriber_email_addresses = ["oncall@example.com"]
  }

  notification {
    comparison_operator = "GREATER_THAN"
    threshold           = 100  # alert at 100% (over budget)
    threshold_type      = "PERCENTAGE"
    notification_type   = "FORECASTED"
    subscriber_email_addresses = ["cto@example.com"]
  }
}
```

---

## Quick Wins Checklist

| Action | Typical Saving |
|--------|---------------|
| Spot instances for workers | 70-90% on worker compute |
| RDS Reserved 1yr | 40% on DB cost |
| S3 Intelligent Tiering | 20-70% on storage |
| S3 lifecycle rules (delete temp) | Eliminate waste |
| PgBouncer (smaller DB instance) | 30-60% on DB |
| Right-size with VPA recommendations | 20-40% on compute |
| GZip compression | Reduce transfer costs |
| Cache TTL tuning (hit rate > 80%) | Reduce DB instance size |
| Delete unused EBS snapshots | Eliminate waste |
| NAT Gateway → VPC endpoints | Reduce transfer costs |

## Cost Optimization Checklist

- [ ] Spot instances for ARQ workers
- [ ] On-demand for API (can't afford interruption)
- [ ] RDS Reserved Instance purchased (after stable sizing)
- [ ] S3 Intelligent Tiering enabled
- [ ] S3 lifecycle rules for temp/exports
- [ ] PgBouncer reducing DB connection count
- [ ] VPA recommendations applied to resource requests
- [ ] GZip middleware enabled
- [ ] Cache hit rate > 80% (alert if drops)
- [ ] AWS Cost Anomaly Detection configured
- [ ] Monthly budget alerts at 80% and 100%
- [ ] Cost reviewed monthly in engineering sync
