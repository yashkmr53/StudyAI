# Troubleshooting — final additions over prior guides

Prior guides: phase_5/6/7 troubleshooting docs cover uploads, OCR/index jobs, PDFs, locks. New Phase 8 entries:

## 429 RATE_LIMITED on login/chat/enrich

- **Cause:** scoped throttle (auth 30/min · ai 120/min) or daily AI budget exhausted.
- **Fix:** wait for the window/day; operators can raise rates/budget via settings. Check Retry-After header for throttle windows.

## /readyz returns 503 degraded

Database unreachable — see Postgres entries in the phase_1 guide.

## Enrichment/chat fails with "All LLM providers failed"

Both chain members failed. Inspect ProviderCallLog rows / job last_error. With mocks this only happens if the chain is configured as ["failing", …].

## Backup verify fails

- Ensure pg_dump/pg_restore binaries match server major version.
- Scratch DB name must differ from live (`verify_backup` refuses same-name targets).

## Status endpoint 403

Requires `is_staff=True`. Set via createsuperuser or admin.
