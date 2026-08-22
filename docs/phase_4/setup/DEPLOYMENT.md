# Deployment — after Phase 4

Reality unchanged: **Development only** (see [`../phase_3/setup/DEPLOYMENT.md`](../setup/DEPLOYMENT.md)).

Phase 4 additions for deployment planning:

| Item | Detail |
|---|---|
| Fonts | `backend/assets/fonts/` must ship inside the image/bundle (they are committed to the repo) |
| Storage volume | PDF artifacts join images on the persistent `OBJECT_STORAGE_LOCAL_DIR` volume |
| Worker | `pdf_render` jobs run through the same executor/worker story as `ocr` — no new infrastructure |
| Perf | §75 target (small note PDF < 10 s) met informally; verify under load in staging |

Still no staging environment, no Docker/compose/nginx artifacts.
