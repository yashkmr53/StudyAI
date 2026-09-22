# StudyAI

StudyAI is an AI-powered learning platform that transforms handwritten study notes into searchable, reference-backed, enriched study material.

Students upload photographs or scans of their handwritten notes. StudyAI transcribes them using vision-capable local models, performs semantic gap analysis against trusted reference textbooks, enriches missing or underdeveloped concepts, and grounds every addition with verified textbook citations.

---

## 1. Product Flow

The core user journey is centered on enriching student notes against authoritative textbooks:

```text
User
  │
  ▼
Handwritten Note (Image Upload)
  │
  ▼
OCR / Visual Understanding (qwen3.5:4b)
  │
  ▼
Stored Document Revision
  │
  ▼
Reference Retrieval (pgvector + tsvector hybrid search)
  │
  ▼
Gap Detection (qwen3.5:4b)
  │
  ▼
Enrichment Generation (qwen3.5:4b)
  │
  ▼
Citation & Evidence Verification
  │
  ▼
Persistent Enriched Note
  │
  ▼
User Profile & Subject Workspace
```

---

## 2. Core Features

### Handwritten Note Ingestion & OCR
- **Image Upload:** Supports PNG, JPEG, and WebP uploads of handwritten notebook pages.
- **Visual Transcription:** Uses multimodal vision model `qwen3.5:4b` to transcribe handwriting and structural headings without third-party cloud APIs.
- **Preserved Source Scans:** Original page images are preserved in object storage alongside the transcription lines.
- **Revision Tracking:** Every transcription and edit is tracked as an immutable document revision with line-level indices and confidence scores.
- **Live Status Progression:** Front-end status tracking dynamically transitions through pending, processing, and transcribed states without requiring page reloads.

### Reference-Grounded Enrichment
- **Contextual Retrieval:** User note contents are embedded and matched against ingested textbook corpora using dense vector similarity and full-text keyword ranking.
- **Semantic Gap Analysis:** Analyzes the transcribed note against retrieved reference material to identify missing explanations, omitted theorems, or incomplete derivations.
- **Content Enrichment:** Generates structured explanatory blocks that address identified gaps while strictly maintaining the author's original notes intact.
- **Asynchronous Execution:** Long-running OCR and enrichment tasks run asynchronously via Celery worker processes backed by Redis queues.

### Verifiable Citations
- **In-Place Inspection:** Enriched blocks link directly to cited references via clickable citation chips (`📖 Ref: p. X`).
- **Citation Details:** Cards display the source textbook title, target page number, verified excerpt quote, and verification status (`supported`).
- **View Stability:** Inspecting reference citations displays details directly in-place without triggering navigation or losing place within the note.

### Workspace & Profile Isolation
- **Dual Study Modules:** Supports both `AI_CLASSROOM` (full AI enrichment, practice QA, structured testing) and `NOTE_SPACE` (streamlined digitizer and PDF export).
- **Profile Scoping:** Multiple user profiles exist within an account. Notes, subjects, and folders remain strictly isolated by profile.
- **Session Persistence:** Active profile and module context persist across browser sessions, reloads, and re-login cycles.

### Interactive Chat
- An integrated conversational agent allows students to ask follow-up questions about their notes and reference materials using the same production LLM.

---

## 3. System Architecture

```text
                                  StudyAI Platform
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 │                                               │
                 ▼                                               ▼
     Qwen/Qwen3-Embedding-0.6B                              qwen3.5:4b
                 │                                               │
          Dense Embeddings                              OCR Vision Transcriber
          (1024 dimensions)                                 Chatbot Assistant
                 │                                            Gap Detection
                 ▼                                        Enrichment Generator
        PostgreSQL + pgvector                               Question Generator
                 │                                               │
                 ▼                                               │
        Reference Retrieval ─────────────────────────────────────┘
                 │
                 ▼
        Evidence Verification & Citation Stitching
                 │
                 ▼
        Durable Storage (PostgreSQL & MinIO)
                 │
                 ▼
      User Workspace & Subject Profile
```

---

## 4. Production AI Stack

StudyAI utilizes a unified, local model architecture to eliminate external API costs, prevent data leakage, and ensure reproducible local execution.

| Component | Model / Engine | Implementation | Role & Responsibilities |
|---|---|---|---|
| **Multimodal LLM** | `qwen3.5:4b` | Host Ollama (`/api/chat`) | Handwritten OCR vision transcription, gap analysis, enrichment generation, citation validation, chat interactions |
| **Embeddings** | `Qwen/Qwen3-Embedding-0.6B` | SentenceTransformers (Local PyTorch) | 1024-dimensional dense vectors for notes, textbook chunks, and search queries |
| **Vector Index** | `pgvector` | PostgreSQL Extension | Cosine similarity indexing (`vector_cosine_ops`) for dense vector matching |
| **Orchestration** | LangGraph / LangChain | Python StateGraph | Multi-node workflows for enrichment, evidence verification, and interactive chat |

---

## 5. Retrieval & Enrichment Pipeline

### Retrieval Engine
StudyAI uses a hybrid retrieval mechanism that combines dense semantic search and lexical matching:

1. **Document Chunking:** Reference textbooks and user notes are partitioned into semantic chunks with tracked page numbers and headings.
2. **Dense Vector Search:** Chunks are embedded with `Qwen/Qwen3-Embedding-0.6B` (1024 dimensions) and queried via `pgvector` using cosine distance.
3. **Lexical Search:** PostgreSQL `tsvector` full-text search indexes keywords and technical terms.
4. **Reciprocal Rank Fusion (RRF):** Blends dense ranks and lexical ranks using standard RRF scoring ($k=60$) to select the top-k most relevant evidence candidates.

### Enrichment Workflow
The enrichment workflow executes as an asynchronous LangGraph pipeline inside Celery:

```text
Transcribed User Note
        │
        ▼
[1] Retrieve Chunks         Hybrid search against textbook corpus
        │
        ▼
[2] Draft Summary           Initial synthesis of note concepts
        │
        ▼
[3] Gap Analysis            Identifies missing definitions, proofs, or context
        │
        ▼
[4] Gap Fill                Generates targeted explanations using reference evidence
        │
        ▼
[5] Citation Stitch         Aligns generated statements with source page excerpts
        │
        ▼
[6] Evidence Verification   Validates claims against retrieved citations
        │
        ▼
[7] Format Output           Persists structured blocks to database
```

---

## 6. Technology Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 19, TypeScript, Vite, React Router v7, i18next |
| **State Management** | Zustand (global UI/workspace stores), IndexedDB (`idb` for offline canvas/strokes) |
| **Backend Framework** | Python 3.14 / Django 6.1, Django REST Framework, SimpleJWT |
| **Asynchronous Tasks** | Celery 5.5, Redis 7 |
| **Primary Database** | PostgreSQL 16 with `pgvector` extension |
| **Object Storage** | MinIO (S3-compatible local bucket for image uploads and generated PDFs) |
| **AI Inference** | Native Host Ollama (`qwen3.5:4b`), HuggingFace / SentenceTransformers |
| **Development** | Docker, Docker Compose |
| **Testing** | Vitest, Puppeteer-core, Pytest, Pytest-Django |

---

## 7. Repository Structure

```text
StudyAI/
├── backend/
│   ├── ai/                      # LangGraph workflows, state definitions, prompts, schemas
│   ├── apps/
│   │   ├── accounts/            # User authentication, token management, budget limits
│   │   ├── ai_classroom/        # Enrichment services, tags, practice endpoints
│   │   ├── documents/           # Note documents, pages, revisions, OCR handlers
│   │   ├── profiles/            # Profile-scoped workspaces and module switching
│   │   ├── references/          # Textbook models and ingestion tooling
│   │   ├── retrieval/           # NoteChunk models, pgvector search, hybrid RRF
│   │   └── subjects/            # Subject categories and metadata
│   ├── config/                  # Django settings (dev, test, prod) and Celery routing
│   ├── providers/               # Driver adapters (LLM, OCR, Embeddings, Storage, Email)
│   └── tests/                   # Backend unit and integration test suite
├── frontend/
│   ├── src/
│   │   ├── components/          # UI primitives, layout, subject workspaces, notes
│   │   ├── features/            # Authentication, onboarding, canvas writing
│   │   ├── services/            # API clients for documents, enrichment, profiles
│   │   └── state/               # Zustand stores for workspace, auth, and modules
│   └── tests/                   # Vitest tests and Puppeteer E2E acceptance suites
├── docs/                        # Architectural documentation and phase reports
├── docker-compose.yml           # Local multi-service infrastructure
└── README.md
```

---

## 8. Getting Started

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- [Git](https://git-scm.com/)
- [Ollama](https://ollama.com/) installed and running on the host system

### 1. Clone the Repository
```bash
git clone https://github.com/yashkmr53/StudyAI.git
cd StudyAI
```

### 2. Pull the AI Model
Ensure Ollama is running locally, then pull the multimodal production model:
```bash
ollama pull qwen3.5:4b
```
*(The embedding model `Qwen/Qwen3-Embedding-0.6B` is loaded directly by `sentence-transformers` within the backend service and cached automatically.)*

### 3. Configure Environment Variables
Copy the template configuration file:
```bash
cp .env.example .env
```
Generate secure keys for development:
```bash
# Set DJANGO_SECRET_KEY
python3 -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64))"

# Set POSTGRES_PASSWORD
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"
```
Update `.env` with the generated values.

### 4. Build and Start the Stack
```bash
docker compose up --build
```
Once initialized, the services will be available at:
- **Frontend Application:** `http://localhost:5173`
- **Backend REST API:** `http://localhost:8000`
- **Interactive API Documentation:** `http://localhost:8000/api/docs/`
- **Mailpit Email Web UI:** `http://localhost:8025`
- **MinIO Console:** `http://localhost:9001` (user: `minioadmin`, pass: `minioadmin`)

---

## 9. Typical User Workflow

1. **Sign Up & Profile Setup:** Register an account and configure an `AI_CLASSROOM` study profile.
2. **Subject Selection:** Select or create a target academic subject (e.g., *DSA*).
3. **Upload Note:** Attach a scanned image or photo of handwritten lecture notes.
4. **Automated Transcription:** View the transcribed note as lines are processed by the OCR engine.
5. **Generate Enrichment:** Navigate to the **Enriched** tab and trigger enrichment.
6. **Background Execution:** The system retrieves reference textbook sections, conducts gap detection, and generates structured explanations.
7. **Inspect Citations:** Click citation badges to view verified quotes from the source textbook.
8. **Persistent Access:** Reopen the note at any time across sessions with transcriptions and enrichments fully preserved.

---

## 10. Reliability & Data Isolation Guarantees

- **Profile Isolation:** API requests enforce profile context via the `X-Active-Profile` header. Database queries filter by profile ID, preventing cross-profile data leakage.
- **Idempotency Keys:** OCR and enrichment jobs enforce unique idempotency keys in Redis/PostgreSQL to prevent duplicate LLM runs on the same revisions.
- **Fault-Tolerant Polling:** The frontend enrichment poller handles in-progress `404 Not Found` statuses gracefully and recovers active job IDs from session storage across page refreshes.
- **Provenance Tracking:** Every enrichment block records the model name, provider, prompt versions, and timestamp used in generation.

---

## 11. Testing

### Frontend Test Suite
```bash
cd frontend
npm test -- --run
```

### Frontend Production Build
```bash
cd frontend
npm run build
```

### Backend Test Suite
Runs the comprehensive Django and pytest regression test suite inside the test container:
```bash
docker compose run --rm test
```

### Browser E2E Acceptance Test
Executes the full end-to-end user journey in a real browser session:
```bash
node frontend/tests/e2e/phase9c_acceptance.mjs
```

---

## 12. Current Product Status

The complete end-to-end user journey has been verified against the live Docker stack with real models:

- **Authentication & Profile:** Clean login restoring `AI_CLASSROOM` module and profile scoping.
- **Handwritten Ingestion:** Real handwritten note on Binary Search Trees successfully uploaded.
- **OCR Transcription:** Real-time processing via `qwen3.5:4b` vision completed automatically in 11.0 seconds.
- **Enrichment Generation:** Completed automatically in 91.6 seconds, successfully absorbing 39 in-progress polling checks.
- **Reference Citations:** Correctly rendered in-place citation cards with verified textbook quotes from ingested reference material.
- **Persistence:** Verified after hard browser reloads and direct note URL access in fresh browser tabs.
- **Module Isolation:** Verified zero cross-profile leakage between `NOTE_SPACE` and `AI_CLASSROOM` profiles.

---

## 13. Future Roadmap

- **Extended Mathematical OCR:** Dedicated LaTeX equation extraction for advanced STEM coursework.
- **Multi-Page Document Ingestion:** Bulk PDF textbook ingestion and indexing pipelines.
- **Collaborative Workspaces:** Multi-user shared subjects and peer study groups.
- **Editable Enrichments:** User overrides and manual adjustments to AI-generated blocks.
- **Interactive Practice Tests:** Adaptive quiz generation directly derived from identified study note gaps.

---

## 14. License

This project is currently not licensed for redistribution.
