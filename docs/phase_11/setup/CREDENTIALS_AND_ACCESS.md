# Phase 11 — Credentials and Access

**Date:** 2026-08-23

---

## Overview

This document lists all credentials required for Phase 11 local development and production deployment, where they're stored, and how to obtain them.

---

## Local Development Credentials

### No External Credentials Required ✅

Phase 11 local development works **without any paid API keys or external credentials**.

| Service | Credential | Default Value | Source |
|---------|------------|---------------|--------|
| **MinIO** | Access Key | `minioadmin` | `.env.example` |
| **MinIO** | Secret Key | `minioadmin` | `.env.example` |
| **Mailpit** | None required | — | Auto-starts |
| **Ollama** | None required | — | Auto-starts |
| **Tesseract** | None required | — | In Docker image |
| **sentence-transformers** | None required | — | Auto-downloads model |

### Generated Secrets (Local)
```bash
# Run these commands, add output to .env
DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
POSTGRES_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

### Local Service Access

| Service | URL | Auth |
|---------|-----|------|
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Mailpit UI | http://localhost:8025 | None |
| Ollama API | http://localhost:11434 | None |
| PostgreSQL | localhost:5432 | studyai / (from .env) |
| Redis | localhost:6379 | None |

---

## Production Credentials (Required for Phase 12+)

### Required for Production Deployment

| Credential | Used By | Obtained From | Rotation |
|------------|---------|---------------|----------|
| **OPENAI_API_KEY** | LLM, Embeddings | OpenAI Platform | 90 days |
| **ANTHROPIC_API_KEY** | LLM (alt) | Anthropic Console | 90 days |
| **GOOGLE_VISION_KEY** | OCR | Google Cloud Console | 90 days |
| **AWS_ACCESS_KEY_ID** | S3 Storage | AWS IAM | 90 days |
| **AWS_SECRET_ACCESS_KEY** | S3 Storage | AWS IAM | 90 days |
| **SMTP_PASSWORD** | Email | SendGrid/Mailgun/SES | 90 days |
| **DJANGO_SECRET_KEY** | Django | Generate locally | 180 days |
| **POSTGRES_PASSWORD** | Database | Generate locally | 180 days |

### Credential Details

#### OpenAI
- **Where**: https://platform.openai.com/api-keys
- **Used for**: LLM (`gpt-4o-mini`), Embeddings (`text-embedding-3-small`)
- **Format**: `sk-...`
- **Cost**: Pay-per-token

#### Anthropic (Alternative LLM)
- **Where**: https://console.anthropic.com/
- **Used for**: LLM (`claude-3-haiku`, `claude-3-sonnet`)
- **Format**: `sk-ant-...`

#### Google Cloud Vision
- **Where**: Google Cloud Console > APIs & Services > Credentials
- **Used for**: OCR (handwriting recognition)
- **Format**: Service account JSON or API key
- **Enable**: Cloud Vision API

#### AWS S3
- **Where**: AWS IAM > Users > Security credentials
- **Used for**: Object storage (production)
- **Permissions**: `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:ListBucket`
- **Format**: `AKIA...` / `...`

#### SendGrid (Email)
- **Where**: SendGrid > Settings > API Keys
- **Used for**: Transactional email (production)
- **Format**: `SG....`
- **Permissions**: Mail Send

#### PostgreSQL
- **Where**: Generate locally or use managed DB password
- **Format**: 32+ char random string
- **Rotation**: Update in DB and all env vars simultaneously

#### Django Secret Key
- **Where**: Generate locally
- **Format**: 64-char URL-safe base64
- **Rotation**: Invalidates all sessions/tokens

---

## Access Management

### Local Development
| Role | Access | Method |
|------|--------|--------|
| Developer | All local services | Docker Compose |
| Developer | Source code | GitHub repo |
| Developer | Local DB | `docker compose exec db psql` |
| Developer | Local Redis | `docker compose exec redis redis-cli` |
| Developer | MinIO | http://localhost:9001 |

### Production (Phase 12+)
| Role | Access | Method |
|------|--------|--------|
| Platform Engineer | Kubernetes cluster | kubectl + RBAC |
| Platform Engineer | Cloud console | AWS/GCP/Azure console |
| Backend Developer | Logs/metrics | Grafana/Datadog |
| Backend Developer | Database (read-only) | Read replica |
| Security Engineer | Secrets | Vault/Secrets Manager |
| On-call | Alerts | PagerDuty/Opsgenie |

---

## Secret Storage

### Local Development
```bash
# .env file (gitignored)
# Never commit .env
echo ".env" >> .gitignore
```

### Production Options

#### Option 1: Docker Secrets (Swarm)
```bash
echo "supersecret" | docker secret create django_secret_key -
# In compose: secrets: [django_secret_key]
```

#### Option 2: Kubernetes Secrets
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: studyai-secrets
  namespace: studyai
type: Opaque
stringData:
  DJANGO_SECRET_KEY: "..."
  OPENAI_API_KEY: "..."
  POSTGRES_PASSWORD: "..."
```

#### Option 3: External Secret Manager
- **AWS Secrets Manager**
- **HashiCorp Vault**
- **Google Secret Manager**
- **Azure Key Vault**

#### Option 4: CI/CD Variables
```yaml
# GitHub Actions
# Settings > Secrets and variables > Actions
DJANGO_SECRET_KEY
OPENAI_API_KEY
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
SMTP_PASSWORD
```

---

## Credential Validation

### Pre-Deployment Checklist
```bash
#!/bin/bash
# validate_credentials.sh

check_var() {
    if [ -z "${!1}" ]; then
        echo "❌ MISSING: $1"
        return 1
    else
        echo "✅ OK: $1"
        return 0
    fi
}

# Development (all optional except Django/DB)
check_var "DJANGO_SECRET_KEY"
check_var "POSTGRES_PASSWORD"

# Production (all required)
if [ "$ENVIRONMENT" = "production" ]; then
    check_var "OPENAI_API_KEY"
    check_var "S3_ACCESS_KEY"
    check_var "S3_SECRET_KEY"
    check_var "SMTP_PASSWORD"
    check_var "OCR_API_KEY"
fi
```

---

## Rotation Schedule

| Credential | Frequency | Process |
|------------|-----------|---------|
| API Keys (OpenAI, Anthropic, Google) | 90 days | Generate new in provider console, update secret store, deploy |
| AWS Keys | 90 days | IAM > Rotate, update secret store, deploy |
| SMTP Password | 90 days | Provider console > New API key, update secret store, deploy |
| Django Secret | 180 days | Generate new, update secret store, deploy (invalidates sessions) |
| Database Password | 180 days | Update in DB, update secret store, rolling restart |

### Rotation Procedure
```bash
# 1. Generate new credential in provider console
# 2. Update secret store (Vault, K8s Secret, GitHub Secret)
# 3. Deploy application (rolling restart)
# 4. Verify health checks pass
# 5. Revoke old credential in provider console
# 6. Update documentation
```

---

## Emergency Access

### Break-Glass Procedure
```bash
# If secret manager unavailable:
# 1. Use backup credentials from secure offline storage
# 2. Set as environment variables directly on server
# 3. Restart affected services
# 4. Restore secret manager ASAP

# Offline backup location: [REDACTED - documented in runbook]
```

### Access Revocation (Offboarding)
```bash
# 1. Remove from all secret stores
# 2. Rotate all credentials they had access to
# 3. Audit access logs for anomalies
# 4. Update team access matrix
```

---

## Audit Trail

### Credential Access Logging
```bash
# Cloud provider audit logs
# AWS: CloudTrail > Secrets Manager events
# GCP: Cloud Audit Logs > Secret Manager
# Azure: Activity Log > Key Vault

# Kubernetes: Audit log > Secret get/list events
# Vault: Audit device > Secret read/write
```

### Compliance
- All production credentials accessed via secret manager (audit trail)
- No credentials in source code, Docker images, or config files
- Rotation logs retained for 1 year
- Annual credential hygiene review