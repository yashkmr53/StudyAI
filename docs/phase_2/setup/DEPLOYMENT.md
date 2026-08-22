# Deployment — after Phase 2

Reality unchanged from Phase 1: **Development exists; Staging and Production do not.** Full analysis and production checklist: [`../phase_1/setup/DEPLOYMENT.md`](../../phase_1/setup/DEPLOYMENT.md).

## What Phase 2 changes for deployment planning

- More tables under RLS (canvas sessions/pages/strokes) — the non-superuser production role requirement now covers them too.
- New env var `CANVAS_LOCK_TTL_SECONDS` (optional, default 90).
- Canvas traffic is small JSON writes; no new infrastructure implications.
- Long-lived editor tabs rely on server-authoritative time for lock expiry — ensure reasonable NTP sync on the host (standard practice).
