# Deployment — after Phase 6

Reality unchanged: **Development only** (see [`../phase_5/setup/DEPLOYMENT.md`](../setup/DEPLOYMENT.md)).

New Phase 6 considerations for the future production environment:

| Item | Detail |
|---|---|
| LLM provider | Swap mock for a real provider (§30 decision); credential via env only; egress + latency budgeting required |
| Enrichment cost control | Coalescing window + quota budgets (§21/§74) become mandatory before real-LLM spend |
| Verifier calibration | Thresholds must be calibrated on the labeled dataset before user-facing verdicts are trusted |
| Job volume | enrich jobs join ocr/index/pdf_render — worker capacity planning per §76 stage |
