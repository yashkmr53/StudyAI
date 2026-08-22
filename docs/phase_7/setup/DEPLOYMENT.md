# Deployment — after Phase 7

Reality unchanged: **Development only** (see [`../phase_6/setup/DEPLOYMENT.md`](../setup/DEPLOYMENT.md)).

Phase 7 additions for the future production environment:

| Item | Detail |
|---|---|
| Chat rate limits | Message endpoint is the first unbounded LLM-shaped cost path — throttling mandatory at real-model swap |
| Mastery/planner tuning | Weights and EMA constants should be calibrated from real attempt data |
| Frontend screens | Learning UIs (tests/chat/planner) are API-complete but not yet built into the PWA |
