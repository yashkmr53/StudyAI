# Deployment — after Phase 3

Reality unchanged: **only Development exists** (see [`../phase_2/setup/DEPLOYMENT.md`](../setup/DEPLOYMENT.md) → [`../phase_1/setup/DEPLOYMENT.md`](../../phase_1/setup/DEPLOYMENT.md)). Phase 3 changes for deployment planning:

## New operational requirements when deploying

| Item | Detail |
|---|---|
| Job execution | Choose Celery workers + Redis (set `CELERY_TASK_ALWAYS_EAGER=False`) **or** cron/systemd `manage.py process_jobs --reap --loop` |
| Reaper | Schedule `process_jobs --reap` (or celery beat for `reap_stuck_jobs_task`) |
| Storage volume | `OBJECT_STORAGE_LOCAL_DIR` must be a persistent volume with backup coverage |
| Upload limits | `UPLOAD_MAX_BYTES` + proxy `client_max_body_size` must agree |
| RLS role | Non-superuser app role now also governs documents tables |

No staging environment exists; no deployment artifacts have been authored.
