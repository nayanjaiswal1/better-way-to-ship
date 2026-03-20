# Kubernetes & Terraform

## Kubernetes

### Deployment

```yaml
# k8s/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # one extra pod during deploy
      maxUnavailable: 0  # zero downtime — never take pods down before new ones are ready
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: myapp/api:1.0.0
          ports:
            - containerPort: 8000

          # Resource limits — always set both requests and limits
          resources:
            requests:
              cpu: "250m"      # 0.25 CPU cores guaranteed
              memory: "256Mi"
            limits:
              cpu: "1000m"     # 1 CPU core max
              memory: "512Mi"

          # Readiness probe — pod receives traffic only when ready
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
            failureThreshold: 3

          # Liveness probe — restart pod if it hangs
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 30
            failureThreshold: 3

          # Graceful shutdown — finish in-flight requests
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]  # let load balancer deregister first

          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: api-secrets
                  key: database-url
            - name: SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: api-secrets
                  key: secret-key

      # Distribute pods across nodes — no single point of failure
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api

      terminationGracePeriodSeconds: 30
```

### Secrets

```yaml
# k8s/secrets.yaml — managed by Helm/Terraform/external-secrets, never hardcoded
apiVersion: v1
kind: Secret
metadata:
  name: api-secrets
  namespace: production
type: Opaque
# Values are base64 encoded — managed by external-secrets-operator
# pointing to AWS Secrets Manager / Vault
```

### Service & Ingress

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector:
    app: api
  ports:
    - port: 80
      targetPort: 8000

---
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
spec:
  tls:
    - hosts: [api.example.com]
      secretName: api-tls
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 80
```

### HPA — Autoscaling

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 2     # always at least 2 for HA
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70   # scale up when CPU > 70%
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

### PodDisruptionBudget — safe maintenance

```yaml
# k8s/pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api
spec:
  minAvailable: 2    # always keep at least 2 pods running during node drain
  selector:
    matchLabels:
      app: api
```

---

## KEDA — Event-Driven Autoscaling

HPA scales on CPU/memory — KEDA scales on **what actually matters**: queue depth, request rate, cron schedule.

### Install KEDA

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda --create-namespace
```

### Scale ARQ Workers by Redis Queue Depth

Scale workers to zero when queue is empty. No jobs = no cost.

```yaml
# k8s/keda-arq-worker.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: arq-worker
  namespace: production
spec:
  scaleTargetRef:
    name: arq-worker          # matches Deployment name
  minReplicaCount: 0          # scale to zero — no jobs, no pods
  maxReplicaCount: 20
  cooldownPeriod: 60          # seconds before scaling down
  pollingInterval: 10         # check queue every 10s

  triggers:
    - type: redis
      metadata:
        address: redis:6379
        listName: arq:default  # ARQ default queue key
        listLength: "5"        # 1 worker per 5 queued jobs
        enableTLS: "false"
      authenticationRef:
        name: redis-auth       # reference to TriggerAuthentication below
```

```yaml
# k8s/keda-redis-auth.yaml — separate secrets from ScaledObject
apiVersion: keda.sh/v1alpha1
kind: TriggerAuthentication
metadata:
  name: redis-auth
  namespace: production
spec:
  secretTargetRef:
    - parameter: password
      name: redis-secrets
      key: password
```

```yaml
# k8s/arq-worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: arq-worker
  namespace: production
spec:
  replicas: 1   # KEDA manages this — set initial count only
  selector:
    matchLabels:
      app: arq-worker
  template:
    metadata:
      labels:
        app: arq-worker
    spec:
      containers:
        - name: worker
          image: myapp/api:1.0.0
          command: ["python", "-m", "arq", "app.workers.main.WorkerSettings"]
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2000m"
              memory: "1Gi"
          env:
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: api-secrets
                  key: redis-url
```

### Scale API by HTTP Request Rate

Scale API pods based on actual traffic — not CPU proxy.

```yaml
# k8s/keda-api-http.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: api-http
  namespace: production
spec:
  scaleTargetRef:
    name: api
  minReplicaCount: 2          # never go below 2 for HA
  maxReplicaCount: 50
  cooldownPeriod: 300

  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring:9090
        metricName: http_requests_per_second
        # Scale up when > 100 req/s per pod
        query: |
          sum(rate(http_requests_total{namespace="production",app="api"}[1m]))
          /
          count(kube_pod_info{namespace="production",pod=~"api-.*"})
        threshold: "100"
```

### Cron Scaling — Predictable Traffic

Pre-scale before business hours, scale down overnight.

```yaml
# k8s/keda-api-cron.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: api-cron
  namespace: production
spec:
  scaleTargetRef:
    name: api
  minReplicaCount: 2
  maxReplicaCount: 20

  triggers:
    # Business hours — pre-scale before traffic hits
    - type: cron
      metadata:
        timezone: UTC
        start: "0 8 * * 1-5"    # Mon-Fri 8am UTC
        end:   "0 20 * * 1-5"   # Mon-Fri 8pm UTC
        desiredReplicas: "6"

    # Scale down overnight and weekends
    - type: cron
      metadata:
        timezone: UTC
        start: "0 20 * * 1-5"
        end:   "0 8 * * 1-5"
        desiredReplicas: "2"
```

### Multiple Triggers — ARQ Priority Queues

Scale workers for each queue independently.

```yaml
# k8s/keda-arq-priority.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: arq-worker-priority
  namespace: production
spec:
  scaleTargetRef:
    name: arq-worker-priority
  minReplicaCount: 0
  maxReplicaCount: 10

  triggers:
    - type: redis
      metadata:
        address: redis:6379
        listName: arq:high       # high priority queue
        listLength: "2"          # 1 worker per 2 high-priority jobs
    - type: redis
      metadata:
        address: redis:6379
        listName: arq:email      # email queue
        listLength: "10"
```

### HPA vs KEDA — When to Use Each

| Scenario | Use |
|----------|-----|
| Scale on CPU/memory | HPA |
| Scale on queue depth | KEDA |
| Scale on HTTP req/s (Prometheus) | KEDA |
| Scale to zero | KEDA |
| Cron-based pre-scaling | KEDA |
| ARQ/Celery workers | KEDA (always) |
| Stateless API pods | KEDA (Prometheus trigger) or HPA |

> Keep HPA for the API deployment if KEDA Prometheus trigger is overkill.
> Use KEDA exclusively for all worker deployments — queue depth is always the right metric.

---

## Terraform — Infrastructure as Code

```bash
# terraform/
# ├── main.tf
# ├── variables.tf
# ├── outputs.tf
# ├── modules/
# │   ├── rds/
# │   ├── elasticache/
# │   └── eks/
```

```hcl
# terraform/main.tf
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket = "myapp-terraform-state"
    key    = "production/terraform.tfstate"
    region = "us-east-1"
    encrypt = true
    dynamodb_table = "terraform-lock"  # prevent concurrent applies
  }
}

provider "aws" {
  region = var.aws_region
}
```

```hcl
# terraform/modules/rds/main.tf
resource "aws_db_instance" "main" {
  identifier        = "${var.env}-myapp-db"
  engine            = "postgres"
  engine_version    = "16.1"
  instance_class    = var.db_instance_class    # db.t3.medium for staging, db.r6g.large for prod
  allocated_storage = 100
  storage_encrypted = true
  storage_type      = "gp3"

  db_name  = "myapp"
  username = "myapp"
  password = var.db_password   # from AWS Secrets Manager

  multi_az               = var.env == "production"   # HA only in prod
  backup_retention_period = 30
  deletion_protection    = var.env == "production"

  performance_insights_enabled = true
  monitoring_interval          = 60

  tags = local.common_tags
}
```

```hcl
# terraform/modules/elasticache/main.tf
resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.env}-myapp-redis"
  description          = "MyApp Redis"
  node_type            = "cache.t3.small"
  num_cache_clusters   = var.env == "production" ? 2 : 1  # HA in prod
  engine_version       = "7.0"
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  tags = local.common_tags
}
```

```hcl
# terraform/variables.tf
variable "env" {
  type    = string
  validation {
    condition     = contains(["staging", "production"], var.env)
    error_message = "env must be staging or production"
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "db_instance_class" {
  type = map(string)
  default = {
    staging    = "db.t3.medium"
    production = "db.r6g.large"
  }
}
```

```bash
# Deploy workflow
terraform init
terraform plan -var="env=production" -out=tfplan
terraform apply tfplan

# Never apply without plan review
# Use CI/CD — terraform plan on PR, terraform apply on merge to main
```
