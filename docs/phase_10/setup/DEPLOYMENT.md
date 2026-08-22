# Deployment — Phase 10

**Status:** Updated with beat service, metrics, backup automation

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Nginx     │────►│    API      │────►│  PostgreSQL │
│  (port 80)  │     │  (port 8000)│     │  (port 5432)│
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Redis     │
                    │  (port 6379)│
                    └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌─────────┐ ┌──────────┐ ┌───────────┐
         │ Worker  │ │   Beat   │ │ Frontend  │
         │         │ │ Scheduler│ │  (Nginx)  │
         └─────────┘ └──────────┘ └───────────┘
```

---

## Docker Compose (Production)

### `docker-compose.yml`
```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 10

  api:
    build: ./backend
    restart: unless-stopped
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_started }
    environment: &backend-env
      DJANGO_SETTINGS_MODULE: config.settings.prod
      DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY}
      DJANGO_DEBUG: ${DJANGO_DEBUG}
      DJANGO_ALLOWED_HOSTS: ${DJANGO_ALLOWED_HOSTS}
      DJANGO_SECURE_SSL_REDIRECT: ${DJANGO_SECURE_SSL_REDIRECT}
      DJANGO_SESSION_COOKIE_SECURE: ${DJANGO_SESSION_COOKIE_SECURE}
      DJANGO_CSRF_COOKIE_SECURE: ${DJANGO_CSRF_COOKIE_SECURE}
      DJANGO_HSTS_SECONDS: ${DJANGO_HSTS_SECONDS}
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_HOST: db
      POSTGRES_PORT: ${POSTGRES_PORT}
      POSTGRES_SSLMODE: disable
      CELERY_BROKER_URL: redis://redis:6379/0
      OBJECT_STORAGE_BACKEND: ${OBJECT_STORAGE_BACKEND}
      OBJECT_STORAGE_LOCAL_DIR: var/objectstore
      SIGNED_URL_TTL_SECONDS: ${SIGNED_URL_TTL_SECONDS}
      # Phase 10 additions
      CELERY_BEAT_ENABLED: ${CELERY_BEAT_ENABLED}
      CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS}
      CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS}
      REDIS_THROTTLE_URL: ${REDIS_THROTTLE_URL}
      PROMETHEUS_METRICS_ENABLED: ${PROMETHEUS_METRICS_ENABLED}
      ENRICHMENT_COALESCE_WINDOW_SECONDS: ${ENRICHMENT_COALESCE_WINDOW_SECONDS}
      ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD: ${ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD}
      MAX_PROVIDER_INPUT_CHARS: ${MAX_PROVIDER_INPUT_CHARS}
      DEFAULT_MONTHLY_TOKEN_BUDGET: ${DEFAULT_MONTHLY_TOKEN_BUDGET}
      DEFAULT_MONTHLY_COST_BUDGET_USD: ${DEFAULT_MONTHLY_COST_BUDGET_USD}
    command: sh -c "python manage.py collectstatic --noinput && python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120"
    volumes:
      - objectstore:/app/var/objectstore
      - django_static:/app/var/static
    healthcheck:
      test: ["CMD-SHELL", "python -c 'import urllib.request as u; u.urlopen(\"http://localhost:8000/healthz\", timeout=3)'"]
      interval: 15s
      timeout: 5s
      retries: 12
      start_period: 30s

  worker:
    build: ./backend
    restart: unless-stopped
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_started }
    environment: *backend-env
    command: celery -A config worker -l info
    volumes:
      - objectstore:/app/var/objectstore

  beat:
    build: ./backend
    restart: unless-stopped
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_started }
    environment: *backend-env
    command: celery -A config beat -l info
    volumes:
      - objectstore:/app/var/objectstore

  frontend:
    build: ./frontend
    restart: unless-stopped
    volumes:
      - ./deploy/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - django_static:/var/www/django-static:ro
    ports:
      - "80:80"
      - "443:443"  # TLS termination
    depends_on:
      - api
    healthcheck:
      test: ["CMD-SHELL", "wget -q -O /dev/null http://127.0.0.1/healthz || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 6
      start_period: 10s

volumes:
  pgdata:
  objectstore:
  django_static:
```

---

## Nginx Configuration

### `deploy/nginx.conf`
```nginx
server {
    listen 80;
    listen 443 ssl http2;
    server_name app.example.com;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header Referrer-Policy same-origin;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()";
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'";

    # Static files
    location /static/ {
        alias /var/www/django-static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Media/Object storage
    location /media/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # API
    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    # Health checks
    location /healthz {
        proxy_pass http://api:8000;
        access_log off;
    }

    location /readyz {
        proxy_pass http://api:8000;
        access_log off;
    }

    # Metrics (internal only)
    location /metrics {
        allow 10.0.0.0/8;  # Prometheus network
        deny all;
        proxy_pass http://api:8000;
    }

    # SPA fallback
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

---

## SSL/TLS (Phase 11)

### Certbot (Let's Encrypt)
```bash
# On host with nginx
certbot --nginx -d app.example.com

# Auto-renewal
systemctl enable certbot-renew.timer
```

### Self-Signed (Development)
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deploy/ssl/privkey.pem \
  -out deploy/ssl/fullchain.pem \
  -subj "/CN=localhost"
```

---

## Backup Automation

### Daily Backup
- **Schedule:** 02:30 UTC (Celery Beat `daily_backup` task)
- **Output:** `/backups/studyai_YYYYMMDD_HHMMSS.dump`
- **Offsite:** `backup_offsite_hook.sh` → `$OFFSITE_BACKUP_URI`

### Volume Mounts
```yaml
volumes:
  - objectstore:/app/var/objectstore  # Shared between api, worker, beat
  - django_static:/app/var/static     # Shared between api, frontend
  # Backup directory (host or volume)
  - ./backups:/backups                # Or named volume
```

---

## Monitoring

### Health Endpoints
| Endpoint | Purpose | Auth |
|----------|---------|------|
| `/healthz` | Liveness | None |
| `/readyz` | Readiness | None |
| `/metrics` | Prometheus | Internal only |
| `/api/v1/status` | Internal status | Staff |

### Prometheus Scraping
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'studyai-backend'
    static_configs:
      - targets: ['api:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

### Log Aggregation
```yaml
# docker-compose.override.yml for logging driver
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
  worker:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
  beat:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## Scaling

### Horizontal
```yaml
# Multiple API workers
api:
  deploy:
    replicas: 3
    resources:
      limits:
        cpus: '2'
        memory: 2G

# Multiple workers
worker:
  deploy:
    replicas: 2
```

### Database
- Read replicas for search/analytics
- Connection pooling: PgBouncer

### Redis
- Cluster mode for high availability
- Separate DBs: 0=broker, 1=results, 2=throttle cache

---

## Rollback Procedure

```bash
# 1. Tag current release
git tag -a rollback-$(date +%Y%m%d) -m "Rollback point"

# 2. Revert to previous tag
git checkout <previous-tag>

# 3. Rebuild and deploy
docker compose build
docker compose up -d

# 4. Run migrations (if needed)
docker compose exec backend python manage.py migrate

# 5. Verify health
curl http://localhost/healthz
curl http://localhost/api/v1/healthz

# 6. If database migration rolled back:
#    docker compose exec backend python manage.py migrate <app> <previous-migration>
```

---

## Related Documentation

- `docs/phase_10/setup/LOCAL_SETUP.md` — Development setup
- `docs/phase_10/setup/ENVIRONMENT_AND_SECRETS.md` — All environment variables
- `docs/phase_10/setup/CREDENTIALS_AND_ACCESS.md` — Access control
- `docs/phase_10/operations/BACKUP_AND_RECOVERY.md` — Backup procedures