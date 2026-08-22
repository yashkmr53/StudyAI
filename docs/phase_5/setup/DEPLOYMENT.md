# Deployment — after Phase 5

Reality unchanged: **Development only** (prior analysis: [`../phase_4/setup/DEPLOYMENT.md`](../setup/DEPLOYMENT.md)).

New Phase 5 requirements for the future production environment:

| Item | Detail |
|---|---|
| pgvector extension | Must be installed on the database server (`CREATE EXTENSION vector` needs privileges or a pre-configured trusted extension on managed PG) |
| Migration order | `retrieval/0000` creates the extension before the chunk table — runs automatically at deploy migrate |
| Index maintenance | HNSW + GIN indexes are created by migrations; reindex strategy needed after model swaps |
| Worker story | `index` jobs join `ocr`/`pdf_render` — same Celery/executor choice as documented |
| Model swap plan | Changing `EMBEDDING_MODEL_VERSION`/dimensions requires a re-index migration (column type change) — recipe pending, tracked in KNOWN_LIMITATIONS |

Still no staging environment; no Docker/compose/nginx artifacts.
