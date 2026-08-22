# Observability — after Phase 4

Infrastructure unchanged (request-ID logging; no metrics/health/tracing/alerts): [`../phase_1/operations/OBSERVABILITY.md`](../../phase_1/operations/OBSERVABILITY.md).

Phase 3–4 additions to the log stream:

- OCR completion INFO lines (provider chain, line count, review flag).
- Render completion INFO lines: pdf_ref, byte size, page count.
- Retryable job failures now log full tracebacks at WARNING (`apps.jobs.services`), making render/OCR flakiness diagnosable from server logs alone.
- fontTools chatter silenced below WARNING.

Still absent: queue-depth/retry-rate metrics, health endpoints, error tracking — Phase 8 items.
