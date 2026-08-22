# System Flows — Implemented Only

Every diagram below reflects code that exists. Flows that do **not** exist yet are listed at the end with ❌.

## 1. Registration

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend (RegisterPage)
    participant API as RegisterView
    participant DB as PostgreSQL

    U->>FE: email + password
    FE->>API: POST /api/v1/auth/register
    API->>API: RegisterSerializer validates (Argon2-ready)
    API->>DB: BEGIN
    API->>DB: INSERT accounts_user
    API->>DB: INSERT profiles_profile ("Default")
    API->>DB: COMMIT
    API->>API: RefreshToken.for_user(user)
    API-->>FE: 201 {user, profile, access, refresh}
    FE->>FE: persist tokens + email (localStorage)
    FE-->>U: redirect to app shell
```

Failures: invalid/short password or duplicate email → `422 VALIDATION_ERROR` envelope.

## 2. Login / refresh / logout

```mermaid
sequenceDiagram
    actor U as User
    participant FE as api client
    participant API as Django
    participant DB as token_blacklist tables

    U->>FE: POST /api/v1/auth/login {email,password}
    API-->>FE: 200 {access, refresh}

    Note over FE: later — access expired (401 on a call)
    FE->>API: POST /api/v1/auth/refresh {refresh}
    API->>DB: old refresh blacklisted (rotation)
    API-->>FE: 200 {access, new refresh}
    FE->>API: retry original request once

    U->>FE: sign out
    FE->>API: POST /api/v1/auth/logout {refresh} (Bearer)
    API->>DB: blacklist refresh
    API-->>FE: 204
    FE->>FE: clear tokens, redirect /login
```

If refresh also fails → session-expired handler clears state and routes to `/login`.

## 3. Subject creation (authorization path)

```mermaid
flowchart TD
    A[POST /api/v1/subjects] --> B{JWT valid?}
    B -- no --> C[401 UNAUTHENTICATED envelope]
    B -- yes --> D{profile FK resolves?}
    D -- no --> E[422 VALIDATION_ERROR]
    D -- yes --> F{profile.user == request.user?}
    F -- no --> G[403 FORBIDDEN]
    F -- yes --> H{unique profile,name?}
    H -- no --> I[422 VALIDATION_ERROR]
    H -- yes --> J[201 Subject]
```

List/read isolation is structural: querysets filter `profile__user=request.user`, so foreign rows never match.

## 4. Error envelope & request IDs

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as RequestIDMiddleware
    participant V as DRF view
    participant EH as exception_handler

    C->>MW: request (optional X-Request-ID)
    MW->>V: request with rid=req_<hex>
    V--xEH: raises (domain/DRF/unhandled)
    EH->>EH: map to {code,message,request_id,details}
    EH-->>C: error JSON + X-Request-ID header
    Note over EH: DRF ValidationError → 422 VALIDATION_ERROR<br/>unhandled non-APIError → 500 INTERNAL_ERROR
```

## 5. RLS context binding (used by services/tests today; workers later)

```mermaid
sequenceDiagram
    participant S as Service code
    participant RLS as shared/database/rls.py
    participant PG as PostgreSQL

    S->>RLS: profile_scoped_transaction(profile_id)
    RLS->>PG: BEGIN
    RLS->>PG: SELECT set_config('app.current_profile_id', id, true)
    Note over PG: visible only inside this transaction
    S->>PG: profile-scoped queries
    RLS->>PG: COMMIT
    Note over PG: context gone after commit (verified by test)
```

## 6. Frontend authenticated page load

```mermaid
flowchart LR
    A[App mounts] --> B[loadPersistedTokens from localStorage]
    B --> C[RequireAuth: init store]
    C --> D{access token present?}
    D -- no --> E[/login/]
    D -- yes --> F[GET /profiles]
    F -- ok --> G[render Layout + routes]
    F -- 401 --> H[refresh once]
    H -- ok --> F
    H -- fail --> E
```

## Not yet implemented flows (❌)

Per spec §43–§59 — none of these exist in code:

- Note upload → direct-to-storage upload → finalize → revision creation
- OCR job processing (primary/fallback) → DocumentLine persistence
- OCR review/edit → new immutable revision
- Canvas autosave/outbox sync against backend; heartbeat/takeover fencing
- NoteSpace layout extraction → PDF render → signed download
- Chunking → embedding → hybrid retrieval
- Enrichment pipeline (retrieve→draft→gap→cite→verify) → EnrichedNote persistence
- Tag extraction → stable-tag upsert → TagChangeLog
- Question generation → adaptive test assembly → attempt scoring → mastery update
- Chat: scoped retrieval → LLM → citation verification → persist message
- Revision planner goal/plan generation
- Reference-book admin ingestion
- Job lifecycle endpoints (`GET /jobs/{id}`, cancel)

These will be added to this document as they are implemented.
