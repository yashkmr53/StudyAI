# Credentials and Access — after Phase 5

Still **PostgreSQL-only** plus the newly added **pgvector extension** (system package, not a credential). No external API keys anywhere.

Reference table: [`../phase_3/setup/CREDENTIALS_AND_ACCESS.md`](../../phase_3/setup/CREDENTIALS_AND_ACCESS.md).

Phase 5 notes:
- Embeddings are computed **locally in-process** (hashing provider) — no embedding API account or key.
- Reference books are ingested by an operator command reading local JSON files — no service credentials involved.
