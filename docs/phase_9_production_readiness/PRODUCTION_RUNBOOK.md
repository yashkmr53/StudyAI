# Production Runbook — StudyAI v4.1

Step-by-step guide for deploying and operating the system. Every command is real or explicitly marked `[NOT YET VERIFIED]`.

---

## 1. Infrastructure prerequisites

- Linux VM (Ubuntu 22.04+) with Docker Engine 24+ and Docker Compose v2
- Domain name with DNS A record pointing to the VM public IP
- Ports: 80 (HTTP→HTTPS redirect), 443 (TLS)
- Minimum: 2 GB RAM, 20 GB disk
- TLS certificate (Let's Encrypt via certbot standalone, or cloud-managed)

## 2. Repository deployment

```bash
git clone <repo-url> /opt/studyai
cd /opt/studyai
```

## 3. Environment variables

Create `/opt/studyai/.env`:

```bash
cat > .env <<'ENV'
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(64))">
DJANGO_ALLOWED_HOSTS=studyai.example.com
POSTGRES_DB=studyai
POSTGRES_USER=studyai_app
POSTGRES_PASSWORD=<random-32-chars>
POSTGRES_HOST=db
POSTGRES_SSLMODE=disable
CELERY_BROKER_URL=redis://redis:6379/0
RATE_LIMITING_ENABLED=True
AI_DAILY_BUDGET_PER_PROFILE=100
UPLOAD_SNIFF_MAGIC_BYTES=True
UPLOAD_MAX_BYTES=10485760
SECURE_SSL_REDIRECT=False
ENV
chmod 600 .env
```

> `SECURE_SSL_REDIRECT=False` in compose because nginx terminates TLS.
> Set to `True` only if Django handles its own HTTPS.

## 4. Database

```bash
docker compose up -d db
sleep 5
docker compose exec db psql -U studyai -c "SELECT 1"   # verify running
```

The pgvector/pgvector:pg16 image includes the vector extension.

## 5. Restricted DB role

```bash
docker compose exec db psql -U studyai -d studyai -c "
CREATE ROLE studyai_app LOGIN PASSWORD '<random>';
GRANT CONNECT ON DATABASE studyai TO studyai_app;
GRANT USAGE ON SCHEMA public TO studyai_app;
"
```

Migrations run as superuser; runtime connections use `studyai_app`.

Behavioral RLS probe after migrations:

```bash
docker compose exec db psql -U studyai -d studyai -c "
SET ROLE studyai_app;
SET app.current_profile_id = '';
SELECT count(*) FROM profiles_profile;   -- expect 0 (fail-closed)
RESET ROLE;
SELECT count(*) FROM profiles_profile;   -- expect all rows (superuser bypasses)
"
```

## 6. Start full stack

```bash
docker compose up -d --build
```

Services started:

| Service | Port | Purpose |
|---|---|---|
| frontend | 80 | nginx serving PWA + /api proxy |
| api | internal | gunicorn Django |
| worker | — | Celery worker consuming Redis broker |
| db | internal | PostgreSQL + pgvector |
| redis | internal | Celery broker |

Verify:

```bash
curl http://localhost/healthz   # {"status":"ok"}
curl http://localhost/readyz    # {"status":"ok","database":true}
```

## 7. Migrations

Run automatically by api container startup (`migrate --noinput`). To re-run:

```bash
docker compose exec api python manage.py migrate --noinput
```

## 8. Smoke tests

```bash
# Register a user
TOKEN=$(curl -s -X POST https://studyai.example.com/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"smoke@example.com","password":"s3curePass!x"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['access'])")

# List profiles (should have one "Default")
curl -s https://studyai.example.com/api/v1/profiles \
  -H "Authorization: Bearer $TOKEN"

# Create a subject
PID=$(curl -s https://studyai.example.com/api/v1/profiles \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys;print(json.load(sys.stdin)['results'][0]['id'])")
curl -s -X POST https://studyai.example.com/api/v1/subjects \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"profile\":\"$PID\",\"name\":\"Test Subject\"}"
```

## 9. Backup

```bash
# Daily database backup
docker compose exec api python manage.py backup_database --output-dir /backups

# Copy object storage files
rsync -a /opt/studyai/objectstore/ /backups/objectstore/

# Verify latest backup
LATEST=$(ls -t /backups/*.sql | head -1)
docker compose exec api python manage.py verify_backup --backup-file "$LATEST"
```

## 10. Rollback

```bash
# Revert to previous image
docker compose down
docker compose up -d --no-build
# If schema rollback needed:
docker compose run --rm api python manage.py migrate <app> <previous_migration>
```

## 11. Logs

```bash
docker compose logs -f api worker
# Structured lines include request_id for correlation with client error reports
```

## 12. Monitoring

Current: `/healthz` and `/readyz` polling + `GET /api/v1/status` (staff) for aggregate metrics.

Planned: Prometheus scrape endpoint, Grafana dashboards, alertmanager rules for queue depth/dead-letter thresholds.

---

## Incident response quick reference

| Symptom | First check | Action |
|---|---|---|
| /readyz returns 503 | DB container status | `docker compose logs db` |
| 429 on auth endpoints | Rate limiter active? | Expected under abuse; raise limits via settings if legitimate |
| Jobs stuck in QUEUED | Worker container running? Redis reachable? | Check worker logs; restart if crashed |
| Dead-letter count rising | Inspect job last_error via admin | Fix root cause; manually requeue via process_jobs |
| Disk filling | objectstore volume size | Extend volume or add GC job |
