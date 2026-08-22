# Database Schema — Phase 10

**Status:** Extended with Notebooks, Job coalesced_from, Profile budget fields

---

## New Tables

### Notebooks Module

#### `notebooks_notebook`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK, default gen_random_uuid() |
| profile_id | UUID | FK → profiles_profile(id), CASCADE |
| subject_id | UUID | FK → subjects_subject(id), SET NULL |
| title | VARCHAR(255) | NOT NULL |
| description | TEXT | DEFAULT '' |
| cover_image_ref | VARCHAR(512) | NULL |
| created_at | TIMESTAMPTZ | DEFAULT now() |
| updated_at | TIMESTAMPTZ | DEFAULT now() |

**Indexes:**
- `notebooks_n_profile_0825f1_idx` (profile_id, created_at)

**RLS Policy:** `profile_isolation_notebooks_notebook`
```sql
USING (profile_id::text = current_setting('app.current_profile_id', true))
```

#### `notebooks_notebookpage`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK, default gen_random_uuid() |
| notebook_id | UUID | FK → notebooks_notebook(id), CASCADE |
| page_number | INTEGER | ≥0 |
| canvas_state | JSONB | DEFAULT '{}' |
| created_at | TIMESTAMPTZ | DEFAULT now() |
| updated_at | TIMESTAMPTZ | DEFAULT now() |

**Constraints:**
- `uniq_notebook_page_number` UNIQUE (notebook_id, page_number)

**RLS Policy:** `profile_isolation_notebooks_page`
```sql
USING (EXISTS (
  SELECT 1 FROM notebooks_notebook n 
  WHERE n.id = notebook_id 
  AND n.profile_id::text = current_setting('app.current_profile_id', true)
))
```

#### `notebooks_notebookline`
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK, default gen_random_uuid() |
| page_id | UUID | FK → notebooks_notebookpage(id), CASCADE |
| line_index | INTEGER | ≥0 |
| points | JSONB | NOT NULL |
| color | VARCHAR(20) | DEFAULT '#000000' |
| width | REAL | DEFAULT 2.0 |
| tool | VARCHAR(20) | DEFAULT 'pen' |
| created_at | TIMESTAMPTZ | DEFAULT now() |

**Constraints:**
- `uniq_notebook_page_line_index` UNIQUE (page_id, line_index)

**RLS Policy:** `profile_isolation_notebooks_line`
```sql
USING (EXISTS (
  SELECT 1 FROM notebooks_notebookpage p
  JOIN notebooks_notebook n ON n.id = p.notebook_id
  WHERE p.id = page_id
  AND n.profile_id::text = current_setting('app.current_profile_id', true)
))
```

---

## Modified Tables

### `jobs_job` (Added Column)
| Column | Type | Constraints |
|--------|------|-------------|
| coalesced_from_id | UUID | FK → jobs_job(id), SET NULL, related_name=coalesced_jobs |

**Purpose:** Traceability for enrichment coalescing (B7)

---

### `accounts_userprofile` (Added Columns)
| Column | Type | Constraints |
|--------|------|-------------|
| monthly_token_budget | INTEGER | DEFAULT 100000 |
| monthly_cost_budget_usd | DECIMAL(10,2) | DEFAULT 50.00 |
| current_month_token_usage | INTEGER | DEFAULT 0 |
| current_month_cost_usd | DECIMAL(10,2) | DEFAULT 0 |
| budget_reset_date | TIMESTAMPTZ | NULL |

**Purpose:** Monthly AI budget enforcement (B8)

---

### `audit_providercalllog` (Existing, Enhanced)
| Column | Type | Constraints |
|--------|------|-------------|
| input_tokens | INTEGER | NULL, ≥0 |
| output_tokens | INTEGER | NULL, ≥0 |
| total_tokens | INTEGER | NULL, ≥0 |
| estimated_cost_usd | DECIMAL(10,6) | NULL |
| metadata | JSONB | DEFAULT '{}' |

**New Fields Populated:** Token counts, cost estimates, redactions_count

---

## Migration Files

### `notebooks/0001_initial.py`
- Creates 3 tables with indexes and constraints

### `notebooks/0002_enable_rls.py`
- Enables RLS on 3 tables
- Creates 3 policies (notebook, page, line)

### `jobs/0003_job_coalesced_from.py`
- Adds `coalesced_from` FK to jobs_job

### `accounts/0003_userprofile_budget_fields.py` (Auto-generated)
- Adds 5 budget fields to accounts_userprofile

---

## RLS Policy Summary

| Table | Policy Name | Isolation |
|-------|-------------|-----------|
| notebooks_notebook | profile_isolation_notebooks_notebook | Direct profile_id |
| notebooks_notebookpage | profile_isolation_notebooks_page | Via notebook → profile |
| notebooks_notebookline | profile_isolation_notebooks_line | Via page → notebook → profile |
| documents_document | profile_isolation_documents_document | Direct profile_id |
| documents_documentpage | profile_isolation_documents_page | Via document |
| documents_documentpagerevision | profile_isolation_documents_revision | Via page → document |
| documents_documentline | profile_isolation_documents_line | Via revision → page → document |

**Note:** All policies use `current_setting('app.current_profile_id', true)` set by middleware per request.

---

## Indexes Added

| Table | Index | Columns |
|-------|-------|---------|
| notebooks_notebook | notebooks_n_profile_0825f1_idx | profile_id, created_at |
| notebooks_notebookpage | notebooks_notebookpage_notebook_id_cef1ca52 | notebook_id |
| notebooks_notebookline | notebooks_notebookline_page_id_862fc0d7 | page_id |
| jobs_job | (existing) | status, created_at; job_type, resource_type, resource_id |

---

## Related Documentation

- `docs/phase_10/modules/NOTE_SPACE.md` — Notebooks data model
- `docs/phase_10/modules/AI_CLASSROOM.md` — Job coalesced_from
- `docs/phase_10/backend/BACKGROUND_JOBS.md` — Job model details
- `docs/phase_6/backend/DATABASE_SCHEMA.md` — Base schema