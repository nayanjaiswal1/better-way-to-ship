# Disaster Recovery

## RTO & RPO Targets

| Tier | Service | RTO | RPO | Strategy |
|------|---------|-----|-----|----------|
| **Tier 1** | API + DB | 15 min | 5 min | Hot standby + PITR |
| **Tier 2** | Workers + Cache | 30 min | 15 min | Cold standby |
| **Tier 3** | Analytics | 4 hours | 24 hours | Snapshot restore |

- **RTO** (Recovery Time Objective) — how long until service is restored
- **RPO** (Recovery Point Objective) — how much data can be lost

---

## Database — Point-in-Time Recovery

```bash
# RDS automated backups — enable in Terraform
resource "aws_db_instance" "main" {
  backup_retention_period = 30          # 30 days of backups
  backup_window           = "02:00-03:00"  # UTC — low traffic
  maintenance_window      = "sun:04:00-sun:05:00"

  # Enable PITR (Point-in-Time Recovery) — requires WAL archiving
  # Automatically enabled when backup_retention_period > 0
}
```

```bash
# Restore to a specific point in time
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier prod-myapp-db \
  --target-db-instance-identifier prod-myapp-db-restored \
  --restore-time 2026-03-20T10:00:00Z

# Wait for restore to complete (~15-30 min)
aws rds wait db-instance-available \
  --db-instance-identifier prod-myapp-db-restored

# Verify data integrity on restored instance before promoting
psql -h restored-instance.rds.amazonaws.com -U myapp -d myapp \
  -c "SELECT COUNT(*) FROM users; SELECT MAX(created_at) FROM orders;"
```

---

## Cross-Region Failover

```hcl
# terraform/modules/rds/main.tf — read replica in secondary region
resource "aws_db_instance" "replica" {
  provider                = aws.us-west-2   # secondary region
  replicate_source_db     = aws_db_instance.main.arn
  instance_class          = var.db_instance_class
  storage_encrypted       = true
  backup_retention_period = 7
  skip_final_snapshot     = false

  # Can promote to primary in a DR event (breaks replication)
  # aws rds promote-read-replica --db-instance-identifier replica
}
```

```bash
# DR runbook — promote replica to primary
# Step 1: Confirm primary is truly down (not split-brain)
aws rds describe-db-instances --db-instance-identifier prod-myapp-db \
  --query 'DBInstances[0].DBInstanceStatus'

# Step 2: Promote replica (takes ~2-5 min, breaks replication lag = RPO)
aws rds promote-read-replica \
  --db-instance-identifier prod-myapp-db-replica-us-west-2

# Step 3: Update DNS to point to new primary
aws route53 change-resource-record-sets \
  --hosted-zone-id ZONE_ID \
  --change-batch file://dr-dns-change.json

# Step 4: Scale up API in secondary region (if not already running)
kubectl config use-context us-west-2-cluster
kubectl scale deployment api --replicas=3 -n production

# Step 5: Verify health
curl https://api.example.com/health
```

---

## S3 — Cross-Region Replication

```hcl
# terraform/modules/s3/main.tf
resource "aws_s3_bucket_replication_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  role   = aws_iam_role.replication.arn

  rule {
    id     = "replicate-all"
    status = "Enabled"

    destination {
      bucket        = aws_s3_bucket.uploads_replica.arn  # us-west-2
      storage_class = "STANDARD_IA"                       # cheaper for DR copies
    }
  }
}

# Versioning required for replication
resource "aws_s3_bucket_versioning" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  versioning_configuration { status = "Enabled" }
}
```

---

## Redis — Backup & Restore

```bash
# ElastiCache — enable automatic backups
resource "aws_elasticache_replication_group" "main" {
  snapshot_retention_limit = 7          # 7 days
  snapshot_window          = "03:00-04:00"

  # For critical cache (session store) — use Redis persistence
  # For ephemeral cache — accept data loss on failure
}

# Restore from snapshot
aws elasticache create-replication-group \
  --replication-group-id prod-myapp-redis-restored \
  --snapshot-name prod-myapp-redis-2026-03-20
```

---

## Application — Stateless Design

Stateless apps recover instantly — just restart or scale.

```python
# ✅ Good — all state in DB/Redis, not in memory
@router.get("/users/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user  # fetched from DB on every request

# ❌ Bad — state in process memory (lost on restart)
_user_cache = {}  # don't do this
```

---

## DR Runbook — Full Outage

```markdown
## Full Outage Response (Tier 1)

### T+0 — Detection
- PagerDuty alert fires
- On-call acknowledges within 5 min (PagerDuty escalation)
- Join incident Slack channel #incident-YYYY-MM-DD

### T+5 — Triage
- Check Grafana: is it API, DB, or infra?
- Check AWS Console / CloudWatch for service health
- Check recent deploys: `git log --since="1 hour ago" --oneline`

### T+10 — Mitigation (fastest path first)
1. **Recent deploy?** → Roll back immediately
   ```bash
   kubectl rollout undo deployment/api -n production
   ```
2. **DB connection exhaustion?** → Restart PgBouncer
   ```bash
   kubectl rollout restart deployment/pgbouncer -n production
   ```
3. **Memory/CPU spike?** → Scale up
   ```bash
   kubectl scale deployment api --replicas=10 -n production
   ```
4. **Primary DB down?** → Promote replica (see above)

### T+15 — Communication
- Update status page: statuspage.io
- Notify customers if impact > 5 min
- Template: "We are investigating elevated error rates. Engineers are engaged."

### T+30 — Resolution
- Verify recovery: `curl https://api.example.com/health`
- Check error rate in Grafana (< 0.1%)
- Update status page to "Resolved"
- Customer communication: "The incident has been resolved at HH:MM UTC."

### T+48h — Postmortem
- Timeline of events
- Root cause
- What worked, what didn't
- Action items with owners + deadlines
- Share with team in #postmortems
```

---

## DR Testing Schedule

**Untested DR is not DR.**

```markdown
## DR Test Calendar

### Monthly (automated)
- [ ] Restore latest RDS snapshot to staging, run smoke tests
- [ ] Verify cross-region S3 replication has no lag
- [ ] Confirm backup retention policy is enforced

### Quarterly (manual)
- [ ] Full DR drill: promote read replica, run smoke tests, fail back
- [ ] Restore Redis from snapshot, verify session handling
- [ ] Test DNS failover to secondary region
- [ ] Time each step — compare against RTO targets

### Annually
- [ ] Tabletop exercise: walk through full outage scenario
- [ ] Review and update runbooks
- [ ] Verify on-call rotation and PagerDuty escalation paths
```

```bash
# Monthly automated restore test (run as cron job)
#!/bin/bash
set -euo pipefail

RESTORE_ID="staging-dr-test-$(date +%Y%m%d)"

# Restore latest snapshot
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier prod-myapp-db \
  --target-db-instance-identifier "$RESTORE_ID" \
  --use-latest-restorable-time

# Wait for it
aws rds wait db-instance-available --db-instance-identifier "$RESTORE_ID"

# Run smoke tests
RESTORE_HOST=$(aws rds describe-db-instances \
  --db-instance-identifier "$RESTORE_ID" \
  --query 'DBInstances[0].Endpoint.Address' --output text)

psql -h "$RESTORE_HOST" -U myapp -d myapp -c \
  "SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days';"

# Cleanup
aws rds delete-db-instance \
  --db-instance-identifier "$RESTORE_ID" \
  --skip-final-snapshot

echo "DR restore test passed: $(date)"
```

---

## DR Checklist

### Backup
- [ ] RDS automated backups — 30 day retention
- [ ] PITR enabled — can restore to any second in retention window
- [ ] S3 cross-region replication enabled + verified
- [ ] Redis snapshots — 7 day retention
- [ ] Backup restore tested monthly (automated)

### Recovery
- [ ] Read replica in secondary region — promotion tested
- [ ] DNS TTL set low (60s) for fast failover
- [ ] App is stateless — any pod can serve any request
- [ ] Runbook written, tested, and accessible offline

### Process
- [ ] RTO/RPO targets agreed with stakeholders
- [ ] On-call rotation defined — no single point of failure in humans
- [ ] Status page configured (statuspage.io / BetterUptime)
- [ ] Postmortem process defined and followed
- [ ] Quarterly DR drills scheduled and executed
