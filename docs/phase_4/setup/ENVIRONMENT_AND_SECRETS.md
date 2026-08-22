# Environment and Secrets — after Phase 4

Delta from [`../phase_3/setup/ENVIRONMENT_AND_SECRETS.md`](../setup/ENVIRONMENT_AND_SECRETS.md): one new setting.

| Variable | Required? | Purpose | Default | Used by | Rotation |
|---|---|---|---|---|---|
| `RENDERER_VERSION` | No | NoteSpace PDF renderer identity; part of artifact content hash — bumping it forces regeneration of all future PDFs | `notespace-pdf-v1` | `apps/documents/note_space.py`, `pdf_renderer.py` | Bump on renderer logic changes |

Everything else (Django, Postgres, Celery, storage, reserved AI-provider keys) is unchanged. Vendored DejaVu fonts live in the repo (`backend/assets/fonts/`) — they are assets, not secrets. Secret scan remains clean.
