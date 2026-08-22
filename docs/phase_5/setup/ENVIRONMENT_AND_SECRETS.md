# Environment and Secrets — after Phase 5

Delta from [`../phase_4/setup/ENVIRONMENT_AND_SECRETS.md`](../setup/ENVIRONMENT_AND_SECRETS.md):

| Variable | Required? | Purpose | Default | Used by | Rotation |
|---|---|---|---|---|---|
| `EMBEDDING_PROVIDER` | No | Local embedding provider selector | `hashing` | `providers/registry.py` | n/a (swap = model migration) |
| `EMBEDDING_DIMENSIONS` | No | Vector width; must match any stored embeddings | `384` | models + embedder | Changing invalidates stored vectors — re-index required |
| `EMBEDDING_MODEL_VERSION` | No | Version recorded per chunk | `hashing-384-v1` | indexing/retrieval | Bump ⇒ re-index all chunks |
| `CHUNKER_VERSION` / `CHUNK_WORDS` / `CHUNK_OVERLAP_WORDS` | No | Chunking identity + geometry | v1 / 120 / 30 | `apps/retrieval/services.py` | Bump version ⇒ re-index |
| `RETRIEVAL_RRF_K` / `RETRIEVAL_CANDIDATES` | No | Fusion constant / per-channel depth | 60 / 50 | RetrievalService.search | Tune via evaluation |

Everything else unchanged. pgvector is a system package (not a secret). Secret scan remains clean.
