# Known Limitations — after Phase 3

Carried-over limitations: [`../phase_2/KNOWN_LIMITATIONS.md`](../phase_2/KNOWN_LIMITATIONS.md) (RLS superuser bypass, rate limiting, password-reset stub, localStorage tokens, outbox failure states + debounce, stroke metadata, canvas concurrency/editor tests, multi-tab fencing UX, OpenAPI warnings, coverage unmeasured, no CI/deploy artifacts/health endpoints/audit logging/backups).

## New or changed in Phase 3

| # | Feature | Current state | Expected architecture | Gap | Impact | Suggested next step |
|---|---|---|---|---|---|---|
| 1 | OCR recognition | 🔧 mock providers produce synthetic text | §6 real handwriting → canonical lines | No real provider (§30 open) | All "recognized" content is fake; downstream AI would train/ground on nonsense | Select provider(s); implement protocol impl; swap settings |
| 2 | Review threshold | Hardcoded 0.80 avg confidence | §26 calibrated on labeled validation set | Uncalibrated constant | Review flags may be meaningless for a real provider | Calibrate during evaluation phase |
| 3 | Image normalization | Existence/readability checks only | §47 normalize step | No deskew/denoise/enhance | Real-provider accuracy would suffer | Add Pillow/OpenCV step behind the same interface when a real provider lands |
| 4 | Storage backend | 🟡 local FS + serving views | §23 private S3-compatible bucket | No cloud storage impl; orphaned objects possible on rollback after write | Single-machine only; no versioning/lifecycle | S3-compatible provider + cleanup policy pre-production |
| 5 | Reaper scheduling | ⚠️ function + command flag + beat task defined | §19 periodic reaper | Nothing schedules beat locally; untested | Stuck RUNNING jobs persist without manual runs | Wire beat/cron in deployment config |
| 6 | Document deletion | No user-facing delete | §69 lifecycle rules | Only cascade via profile | Users can't remove documents yet | Delete endpoint + storage GC in hardening |
| 7 | Storage garbage collection | None | §69 raw-upload retention | Orphans from rollbacks/manual uploads | Disk growth in dev; compliance later | Lifecycle job keyed off page.image_ref |
| 8 | Magic-byte validation | Content-Type header trusted | §23 malicious-upload defense | No file-content sniffing | Crafted payloads could masquerade as images | Sniff signatures at upload view |
| 9 | Frontend upload UI | API-only | §63 notespace feature | Users can't upload from UI yet | Ingestion not user-reachable end-to-end | Build with Phase 4 NoteSpace screens |
| 10 | Broker integration test | Eager mode only exercised | §19 worker durability under broker | Celery worker never run against Redis | Execution semantics unproven outside eager | Install Redis; CI service container |

## Non-limitations (deliberate)

- Duplicate finalize returns existing logical job (C-008) — that's the §20 contract.
- Plain-UUID columns avoiding circular FKs / premature cascades (B-015/C-006).
- Simplified rasterizer distinct from NoteSpace renderer (C-005).
