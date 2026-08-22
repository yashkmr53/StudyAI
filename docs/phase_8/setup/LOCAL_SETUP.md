# Local Setup — final

Bootstrap unchanged from Phase 5 ([`../phase_5/setup/LOCAL_SETUP.md`](../../phase_5/setup/LOCAL_SETUP.md)). Phase 8 adds ops commands and a load harness.

## Ops commands (all verified)

```bash
cd backend

# Health & status (server running)
curl -s http://127.0.0.1:8000/readyz          # {"status":"ok","database":true}
curl -s http://127.0.0.1:8000/api/v1/status -H "Authorization: Bearer $STAFF_TOKEN"

# Backup + verified restore drill
../myenv/bin/python manage.py backup_database --output-dir ../backups
../myenv/bin/python manage.py verify_backup --backup-file $(ls -t ../backups/*.sql | head -1)

# Evaluation with regression gate
../myenv/bin/python manage.py run_ai_evaluation --file eval/cases.json --assert-gte support_precision=0.8

# Load baseline vs §75 targets
../myenv/bin/python scripts/load_test.py --base http://127.0.0.1:8000 \
  --email you@example.com --password '…' --n 200 --threads 20
```

## Tests

```bash
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests   # 116 found: 113 pass, 3 skip
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev  ../myenv/bin/python manage.py test tests --noinput    # 116 pass
cd frontend && npm test && npm run build
```
