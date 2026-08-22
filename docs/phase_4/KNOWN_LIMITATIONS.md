# Known Limitations — after Phase 4

Carried over from earlier phases: [`../phase_3/KNOWN_LIMITATIONS.md`](../phase_3/KNOWN_LIMITATIONS.md) (RLS superuser bypass, rate limiting, password-reset stub, localStorage tokens, outbox failure states/debounce, stroke metadata, canvas concurrency + editor test automation, multi-tab fencing UX, OpenAPI warnings, coverage unmeasured, no CI/deploy artifacts/health endpoints/audit logging/backups, mocked OCR, uncalibrated review threshold, image normalization absent, storage GC, magic-byte sniffing).

## New or changed in Phase 4

| # | Feature | Current state | Expected architecture | Gap | Impact | Suggested next step |
|---|---|---|---|---|---|---|
| 1 | PDF text verification | Purity asserted at layout boundary; fpdf2 trusted to embed | Deterministic output checks | No extracted-text assertion in tests | A renderer regression could pass unnoticed | Add pypdf-based round-trip test |
| 2 | CJK glyph coverage | DejaVu lacks CJK | Faithful rendering for all scripts | Chinese/Japanese/Korean lines render as boxes | Blocks those locales | Bundle Noto Sans SC/JP/KR variants |
| 3 | Images inside PDFs | Not supported (sources have none yet) | §49 "images where retained" | Renderer ignores any non-text content | Photos-with-diagrams lose imagery in PDF | Extend line model or add figure refs when sources carry images |
| 4 | Superseded-artifact GC | Old artifacts retained forever | §69 retention policy | Storage growth per edit cycle | Disk usage drift upward | Lifecycle job keyed on digitized rows |
| 5 | Edit UX granularity | Full-page reload after save; no revision diff view | Smooth §48 editing | Crude but correct flow | Developer-grade UX | Richer client state in hardening/UI phase |
| 6 | Perf measurement | <10 s target met informally (ms-scale renders) | §75 engineering objective | No formal perf test | Unknown at scale | Add render benchmark with large documents |

## Non-limitations (deliberate)

- `revision_ids` list instead of singular `revision_id` (D-002).
- Download endpoint returns signed-URL JSON rather than a redirect (D-004).
- Headings only via explicit flags — inference is forbidden for NoteSpace (D-005).
