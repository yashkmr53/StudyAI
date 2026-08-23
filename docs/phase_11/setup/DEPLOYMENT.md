# Phase 11 — Deployment

**Date:** 2026-08-23

---

## Overview

Phase 11 local-first architecture runs entirely in Docker Compose. Production deployment requires additional infrastructure.

---

## Local Development Deployment

### Docker Compose (Single Host)
```bash
# Start
docker compose up -d

# Scale workers
docker compose up -d --scale worker=4

# View logs
docker compose logs -f api
```

### Service Dependencies
```
api/worker/beat depends on: db, redis, minio, mailpit, ollama
frontend depends on: api
```

### Health Checks
```yaml
# All services have healthchecks
# api: curl /healthz
# db: pg_isready
# redis: redis-cli ping
# minio: curl /minio/health/live
# mailpit: wget /
# ollama: ollama list
```

---

## Production Deployment Options

### Option 1: Docker Compose (Single Server)
```bash
# Use production compose file
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Production overrides:
# - Remove port bindings from internal services
# - Add resource limits
# - Use production env file
# - Enable SSL termination
```

### Option 2: Kubernetes
```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: studyai

---
# k8s/deployment-api.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: studyai
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: studyai/api:latest
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: studyai-secrets
        - configMapRef:
            name: studyai-config
        readinessProbe:
          httpGet:
            path: /readyz
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

### Option 3: Cloud Managed Services
| Service | Local | Production |
|---------|-------|------------|
| PostgreSQL | pgvector container | RDS / Cloud SQL / Managed pgvector |
| Redis | Redis container | ElastiCache / Memorystore |
| MinIO | MinIO container | S3 / GCS / R2 |
| Mailpit | Mailpit container | SendGrid / Mailgun / SES |
| Ollama | Ollama container | OpenAI / Anthropic / Vertex AI |

---

## Production Configuration

### Environment File (`.env.production`)
```bash
# Django
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<from secret manager>
DJANGO_ALLOWED_HOSTS=app.studyai.com,api.studyai.com
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SESSION_COOKIE_SECURE=1
DJANGO_CSRF_COOKIE_SECURE=1
DJANGO_HSTS_SECONDS=31536000

# Database (managed)
POSTGRES_DB=studyai
POSTGRES_USER=studyai
POSTGRES_PASSWORD=<from secret manager>
POSTGRES_HOST=db.studyai.internal
POSTGRES_PORT=5432
POSTGRES_SSLMODE=require

# Redis (managed)
CELERY_BROKER_URL=rediss://redis.studyai.internal:6379/0
REDIS_THROTTLE_URL=rediss://redis.studyai.internal:6379/2

# Providers (Production)
STORAGE_BACKEND=s3
S3_BUCKET=studyai-prod
S3_REGION=us-east-1
S3_ACCESS_KEY=<from secret manager>
S3_SECRET_KEY=<from secret manager>
S3_SECURE=true

OCR_PROVIDER_CHAIN=google,mock
OCR_API_KEY=<from secret manager>

LLM_PROVIDER_CHAIN=openai,mock
OPENAI_API_KEY=<from secret manager>
LLM_MODEL=gpt-4o-mini

EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=<from secret manager>
EMBEDDING_MODEL_NAME=text-embedding-3-small

EMAIL_BACKEND=smtp
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=<from secret manager>
SMTP_USE_TLS=true
EMAIL_FROM=noreply@studyai.com

# Security
CORS_ALLOWED_ORIGINS=https://app.studyai.com
CSRF_TRUSTED_ORIGINS=https://app.studyai.com
RATE_LIMITING_ENABLED=true
PROMETHEUS_METRICS_ENABLED=true
```

---

## TLS/SSL Termination

### Nginx (Recommended)
```nginx
# /etc/nginx/sites-available/studyai
server {
    listen 80;
    server_name app.studyai.com api.studyai.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name app.studyai.com;
    
    ssl_certificate /etc/letsencrypt/live/app.studyai.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.studyai.com/privkey.pem;
    
    location / {
        proxy_pass http://frontend:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl http2;
    server_name api.studyai.com;
    
    ssl_certificate /etc/letsencrypt/live/api.studyai.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.studyai.com/privkey.pem;
    
    location / {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Certificates (Let's Encrypt)
```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificates
sudo certbot --nginx -d app.studyai.com -d api.studyai.com

# Auto-renewal
sudo certbot renew --dry-run
# Add to cron: 0 0 * * * certbot renew --quiet
```

---

## Resource Requirements

### Local Development
| Service | CPU | Memory | Disk |
|---------|-----|--------|------|
| db | 1 core | 1 GB | 5 GB |
| redis | 0.5 core | 256 MB | 1 GB |
| minio | 1 core | 512 MB | 10 GB |
| mailpit | 0.5 core | 128 MB | 1 GB |
| ollama | 2 cores | 6 GB | 10 GB (models) |
| api | 1 core | 1 GB | 2 GB |
| worker | 1 core | 1 GB | 2 GB |
| beat | 0.5 core | 256 MB | 1 GB |
| frontend | 0.5 core | 128 MB | 500 MB |
| **Total** | **~8 cores** | **~11 GB** | **~30 GB** |

### Production (Estimated)
| Service | CPU | Memory | Replicas |
|---------|-----|--------|----------|
| api | 2 cores | 2 GB | 3 |
| worker | 2 cores | 2 GB | 4 |
| beat | 0.5 core | 512 MB | 1 |
| frontend (nginx) | 0.5 core | 256 MB | 2 |

---

## CI/CD Pipeline

### GitHub Actions (`.github/workflows/deploy.yml`)
```yaml
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  test:
    uses: ./.github/workflows/ci.yml
    
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Build images
        run: |
          docker build -t studyai/api:${{ github.sha }} ./backend
          docker build -t studyai/frontend:${{ github.sha }} ./frontend
      
      - name: Push to registry
        run: |
          echo ${{ secrets.REGISTRY_TOKEN }} | docker login ghcr.io -u ${{ github.actor }} --password-stdin
          docker push ghcr.io/${{ github.repository }}/api:${{ github.sha }}
          docker push ghcr.io/${{ github.repository }}/frontend:${{ github.sha }}
      
      - name: Update Kubernetes
        run: |
          kubectl set image deployment/api api=ghcr.io/${{ github.repository }}/api:${{ github.sha }} -n studyai
          kubectl set image deployment/frontend frontend=ghcr.io/${{ github.repository }}/frontend:${{ github.sha }} -n studyai
          kubectl rollout status deployment/api -n studyai
          kubectl rollout status deployment/frontend -n studyai
```

---

## Monitoring & Alerting

### Prometheus Metrics (Already Implemented)
```bash
# Metrics endpoint
curl http://localhost:8000/metrics

# Key metrics:
# - http_requests_total
# - ocr_fallback_total
# - schema_validation_failure_total
# - retrieval_latency_seconds
# - evaluation_score
# - product_usage_total
```

### Recommended Alerts
```yaml
# Prometheus alert rules
groups:
- name: studyai
  rules:
  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "High error rate on {{ $labels.instance }}"
      
  - alert: OllamaDown
    expr: up{job="ollama"} == 0
    for: 1m
    labels:
      severity: critical
      
  - alert: MinIODown
    expr: up{job="minio"} == 0
    for: 1m
    labels:
      severity: critical
      
  - alert: BackupFailed
    expr: increase(backup_failed_total[1h]) > 0
    labels:
      severity: warning
```

---

## Backup Strategy (Production)

### Automated Daily Backup
```bash
# Cron job on backup server
0 2 * * * /opt/studyai/backup.sh >> /var/log/studyai-backup.log 2>&1
```

### Cross-Region Replication
```bash
# S3 Cross-Region Replication for RPO < 24h
aws s3control put-bucket-replication --bucket studyai-prod-backups \
  --replication-configuration file://replication-config.json
```

---

## Rollback Procedure

### Application Rollback
```bash
# Kubernetes
kubectl rollout undo deployment/api -n studyai
kubectl rollout undo deployment/frontend -n studyai

# Docker Compose
docker compose pull api:previous-tag
docker compose up -d api
```

### Database Rollback
```bash
# From backup
docker compose run --rm api python manage.py restore_database \
  --backup-dir s3://studyai-prod-backups/2024-01-15
```

### Provider Rollback
```bash
# Revert to mock providers instantly
# Update .env:
OCR_PROVIDER_CHAIN=mock,mock
LLM_PROVIDER_CHAIN=mock,mock
EMBEDDING_PROVIDER=hashing
EMAIL_BACKEND=console

docker compose restart api worker beat
```

---

## Disaster Recovery

### RPO/RTO Targets
| Tier | RPO | RTO |
|------|-----|-----|
| Critical (User Data) | 1 hour | 2 hours |
| Standard (App Config) | 24 hours | 4 hours |

### DR Checklist
- [ ] Backup destination in different region
- [ ] Restore procedure tested quarterly
- [ ] Runbook documented and accessible
- [ ] Team trained on restore procedure
- [ ] Monitoring alerts for backup failures