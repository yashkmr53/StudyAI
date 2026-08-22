# Credentials and Access — after Phase 2

No changes from Phase 1: the system still requires **only PostgreSQL**. No external service accounts, API keys, or credentials exist anywhere in Phase 2 code.

Full table (PostgreSQL / Redis / object storage / OCR / LLM / embedding / email / monitoring): [`../phase_1/setup/CREDENTIALS_AND_ACCESS.md`](../../phase_1/setup/CREDENTIALS_AND_ACCESS.md).

Phase 2 note: canvas sync is plain authenticated HTTPS to the Django API using the same JWT credentials issued at login — no additional access mechanisms were added.
