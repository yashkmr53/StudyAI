# Credentials & Access — Phase 10

**Status:** Extended with new service accounts and access patterns

---

## Service Accounts

### Database
| Account | Purpose | Access |
|---------|---------|--------|
| `studyai` (app) | Django ORM | Read/Write all tables |
| `studyai_migrate` | Migrations | DDL + DML |
| `studyai_readonly` | Analytics/Reporting | Read-only |
| `postgres` | Admin | Superuser |

### Redis
| Account | Purpose | Access |
|---------|---------|--------|
| `default` | Celery broker (DB 0) | Read/Write |
| `default` | Results backend (DB 1) | Read/Write |
| `default` | Throttle cache (DB 2) | Read/Write |

### Object Storage
| Account | Purpose | Access |
|---------|---------|--------|
| `studyai_app` | Django storage | Read/Write bucket |
| `studyai_backup` | Backup offsite | Write-only bucket/prefix |

### External AI Providers (Phase 11)
| Provider | Account | Credentials |
|----------|---------|-------------|
| OCR | Vendor API | `OCR_API_KEY` |
| LLM | Vendor API | `LLM_API_KEY` |
| Embeddings | Local/HuggingFace | `EMBEDDING_MODEL_PATH` |

### Monitoring
| Account | Purpose | Access |
|---------|---------|--------|
| `prometheus` | Metrics scraping | `/metrics` endpoint |
| `grafana` | Dashboards | Read-only DB, Prometheus |
| `alertmanager` | Alerting | Alertmanager config |

---

## Access Patterns

### Backend Services
| Service | DB | Redis | Object Storage | External APIs |
|---------|----|-------|----------------|---------------|
| API | R/W | R/W (broker, throttle) | R/W | OCR, LLM (Phase 11) |
| Worker | R/W | R/W (broker) | R/W | OCR, LLM |
| Beat | R/W | R/W (broker) | R (backup) | pg_dump |

### Frontend
| Service | Access |
|---------|--------|
| Nginx | Static files, proxy to API |
| Browser | API via HTTPS, WS for canvas |

### CI/CD
| Stage | Access |
|-------|--------|
| Test | DB (test), Redis (test) |
| Build | Docker registry (push) |
| Deploy | Docker host, secrets |
| Monitoring | Prometheus, DB (readonly) |

---

## Credential Types

### Long-Lived
| Credential | Rotation | Storage |
|------------|----------|---------|
| `DJANGO_SECRET_KEY` | Annual | Vault/Secrets Manager |
| `POSTGRES_PASSWORD` | Quarterly | Vault |
| `CELERY_BROKER_URL` (Redis password) | Quarterly | Vault |
| `OFFSITE_BACKUP_URI` credentials | Quarterly | Vault |
| `OCR_API_KEY` | Per vendor | Vault |
| `LLM_API_KEY` | Per vendor | Vault |

### Short-Lived
| Credential | TTL | Issuer |
|------------|-----|--------|
| JWT Access Token | 30 min | Django (SimpleJWT) |
| JWT Refresh Token | 14 days | Django (SimpleJWT) |
| Signed Upload URL | 5 min | Django (StorageProvider) |
| Signed Download URL | 5 min | Django (StorageProvider) |
| Password Reset Token | 1 hour | Django (custom) |

---

## Access Control

### Role-Based Access

#### Platform Engineer
- All infrastructure credentials
- Vault admin access
- Docker/host access
- Cloud provider admin

#### Backend Developer
- DB (dev/staging)
- Redis (dev/staging)
- Vault read (dev/staging)
- Docker registry (push dev images)

#### Frontend Developer
- None (frontend only)
- API access via dev backend

#### SRE/On-Call
- Vault read (all envs)
- DB read (prod)
- Redis read (prod)
- Cloud provider read
- Log aggregation access
- Alertmanager config

#### CI/CD Pipeline
- Vault read (deploy env)
- Docker registry (push/pull)
- Kubernetes/Docker host (deploy)
- Notification webhooks (Slack, PagerDuty)

### Principle of Least Privilege
- No shared credentials between services
- Each service has dedicated DB user
- Redis DB separation (0=broker, 1=results, 2=throttle)
- Object storage per-service prefixes

---

## Network Access

### Firewall Rules
| Source | Destination | Port | Protocol |
|--------|-------------|------|----------|
| Internet | Nginx | 80, 443 | TCP |
| Nginx | API | 8000 | TCP |
| API | DB | 5432 | TCP |
| API/Worker/Beat | Redis | 6379 | TCP |
| API | Object Storage | 443 | HTTPS |
| Prometheus | API | 8000 | TCP (`/metrics`) |
| Grafana | Prometheus | 9090 | TCP |
| Alertmanager | Alertmanager | 9093 | TCP |

### VPN/Zero Trust
- All internal traffic via private network
- No public access to DB, Redis, internal APIs
- Admin access via VPN + MFA
- Database admin via bastion host

---

## Audit & Compliance

### Credential Access Logging
- Vault/AWS Secrets Manager: All access logged
- Cloud provider: IAM access logs
- Database: `log_connections = on`, `log_statement = 'ddl'`
- Redis: `notify-keyspace-events` for sensitive keys

### Periodic Reviews
| Review | Frequency | Owner |
|--------|-----------|-------|
| Active credentials | Monthly | Platform Engineer |
| Service account permissions | Quarterly | Platform Engineer |
| API key usage | Monthly | Platform Engineer |
| Vault audit log | Weekly | SRE |
| Expired/rotated secrets | Monthly | Platform Engineer |

### Incident Response
1. **Credential Compromise:**
   - Immediate rotation
   - Audit access logs
   - Notify affected parties
   - Post-incident review

2. **Unauthorized Access:**
   - Revoke compromised credentials
   - Block source IP/network
   - Forensic analysis
   - Compliance notification (if required)

---

## Credential Delivery

### Development
```bash
# .env file (gitignored)
cp .env.example .env
# Edit with local values
```

### CI/CD
```yaml
# GitHub Actions secrets
secrets:
  DJANGO_SECRET_KEY
  POSTGRES_PASSWORD
  CELERY_BROKER_URL
  OFFSITE_BACKUP_URI
  OCR_API_KEY
  LLM_API_KEY
```

### Production
```bash
# Vault path: secret/studyai/prod/
# Injected via envconsul or vault-agent-injector

# Or Docker secrets
services:
  api:
    secrets:
      - django_secret_key
      - postgres_password

secrets:
  django_secret_key:
    external: true
  postgres_password:
    external: true
```

---

## Emergency Access

### Break-Glass Procedure
1. Platform engineer requests emergency access via PagerDuty
2. Vault generates time-limited token (1 hour)
3. Access granted with full audit trail
4. Automatic revocation after expiry
5. Post-access review within 24 hours

### Offline Recovery
- Backup encryption keys stored in physical safe
- Root DB credentials in sealed envelope
- Recovery procedure documented in runbook

---

## Related Documentation

- `docs/phase_10/setup/ENVIRONMENT_AND_SECRETS.md` — All environment variables
- `docs/phase_10/setup/DEPLOYMENT.md` — Production deployment
- `docs/phase_10/setup/LOCAL_SETUP.md` — Development setup
- `docs/phase_10/operations/BACKUP_AND_RECOVERY.md` — Backup credentials