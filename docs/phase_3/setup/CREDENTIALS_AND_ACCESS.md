# Credentials and Access — after Phase 3

Unchanged from prior phases: **PostgreSQL is the only required service.** Full table: [`../phase_2/setup/CREDENTIALS_AND_ACCESS.md`](../setup/CREDENTIALS_AND_ACCESS.md) → [`../phase_1/setup/CREDENTIALS_AND_ACCESS.md`](../../phase_1/setup/CREDENTIALS_AND_ACCESS.md).

Phase 3 notes:

- OCR runs on in-process mock providers — no external OCR account/credentials exist.
- Object storage is the local filesystem — no bucket credentials.
- Redis still not installed: dev/test run jobs eagerly, and `manage.py process_jobs` provides broker-free execution.
- All storage access flows through HMAC-signed URLs derived from the Django secret key.
