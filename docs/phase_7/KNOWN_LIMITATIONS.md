# Known Limitations — after Phase 7

Carried over: [`../phase_6/KNOWN_LIMITATIONS.md`](../phase_6/KNOWN_LIMITATIONS.md) (RLS superuser bypass, rate limiting, password-reset stub, localStorage tokens, outbox failure states/debounce, stroke metadata, concurrency/editor tests, multi-tab UX, OpenAPI warnings, coverage unmeasured, no CI/deploy/health/audit/backups, mocked OCR+LLM text, image normalization absent, storage GC, magic-byte sniffing, hashing embeddings + CJK gaps, verifier calibration absent, eval datasets empty).

## New or changed in Phase 7

| # | Feature | Current state | Expected architecture | Gap | Impact | Suggested next step |
|---|---|---|---|---|---|---|
| 1 | Question quality | 🔧 deterministic MCQs restructure evidence; distractors may be weak | §54 LLM-authored questions w/ plausible distractors | No reasoning-based distractors | Practice value limited until real model | Swap LLM provider; keep schemas |
| 2 | Mastery constants | EMA factors fixed (0.4 gain / decay) | Calibrated scoring | Untuned against real attempt distributions | Mastery levels approximate | Calibrate on accumulated attempts (§26) |
| 3 | Single tag per question | One concept link per question (G-004) | Multi-concept questions | Mastery attribution coarse for multi-topic items | Fine-grained adaptivity limited | Allow M2M links when tagging matures |
| 4 | Difficulty targeting | Static medium from mock; selection bonus only | Adaptive difficulty ladder | No difficulty escalation logic | Tests don't ramp difficulty | Add mastery-driven difficulty policy post-calibration |
| 5 | Chat answer synthesis | Extractive top-evidence snippet | Grounded generative answer | No synthesis across evidence pieces | Answers can be terse | Real-LLM swap; keep verifier gate |
| 6 | Planner session count | Fixed 2/day, ≤14-day horizon | Hours-per-week driven scheduling | hours_per_week captured but not yet used to scale sessions | Plan ignores stated availability | Derive sessions/day from hours_per_week |
| 7 | Tag rename API | Service-level only | Admin capability | No endpoint/UI for renames | Renames require shell access | Expose admin endpoint in hardening |
| 8 | Frontend learning UIs | ❌ API-only (tests/chat/planner) | §63 features screens | Users reach these via curl only | Not demoable end-user side | Build with final UI phase |

## Non-limitations (deliberate)

- not_assessed ≠ zero anywhere in the codebase (§18).
- Attempts immutable + replay → 409 (G-007).
- Plans computed on read; goals persisted (G-010).
