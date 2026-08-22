# KNOWN_LIMITATIONS — final after Phase 8

Carried-over limitations from earlier phases remain tracked in [`../phase_7/KNOWN_LIMITATIONS.md`](../phase_7/KNOWN_LIMITATIONS.md). This page lists what is still open **after Phase 8 hardening**, with the new items first.

## Phase 8 additions/changes

| # | Item | Current state | Expected | Gap | Impact | Next step |
|---|---|---|---|---|---|---|
| 1 | Backup automation | Commands + verified drill exist; nothing schedules them | §70 daily + offsite | No cron/systemd; objectstore dir copy manual | Data-loss window = ∞ until scheduled | Add timer + offsite copy at deploy |
| 2 | CI execution | Workflow authored (.github/workflows/ci.yml) | Green CI on push | Never run on GitHub | Regressions undetected remotely | Push repo; iterate on workflow |
| 3 | Compose stack drill | Artifacts authored; never run on clean host | §24 single-VM stack | Runtime config issues possible (env, fonts, migrations) | Deploy risk | Execute compose up drill on a VM |
| 4 | Distributed throttle store | LocMem cache per process | Shared cache for multi-node | Limits don't aggregate across nodes | Only matters >1 node | Swap cache backend at deploy |
| 5 | Metrics depth | In-process histogram, resets on restart; no export format | §25 metrics + APM/alerting | No history or alerts | Ops blind spots between deploys | Export via /status scraping now, APM later |
| 6 | Password reset email | Stubbed 202 | Full reset flow | Users cannot self-recover | UX/compliance gap | Token model + email backend |
| 7 | RLS behavioral proof | Policies live; dev superuser bypasses | Enforced isolation | Restricted-role test pending | Isolation rests on app layer today | Non-superuser role + policy tests |
| 8 | AI content quality | 🔧 mock OCR/LLM everywhere | Real transcription/generation | Synthetic text end-to-end | Product value blocked on provider decisions (§30) | Provider selection + swap (registries ready) |
| 9 | Calibration | Verifier thresholds, mastery EMA, RRF k all defaults | Calibrated on labeled data | Arbitrary constants | Quality unknown | Author golden set; run regression gate in CI |
| 10 | Magic-byte coverage | PNG/JPEG/WebP signatures only | Full content validation | Other types unvalidated | Minor | Extend signature map with new types |

## Standing ❌ list (unchanged scope)

Notebooks endpoint group · reranking stage · coalescing-window scheduling · question/chat eval runners · tags rename API/UI · learning-layer frontend screens beyond placeholders · rate-limit distributed store · managed services migration.

## Deliberate deviations (documented, not defects)

All recorded across ASSUMPTIONS_AND_DECISIONS.md files: sequential orchestration instead of LangGraph, revision_ids lists, signed-URL JSON payloads, budget-as-call-count proxy, local-FS storage variant, hashing embeddings.
