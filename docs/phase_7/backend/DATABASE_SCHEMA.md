# Database Schema — after Phase 7

Delta from Phase 6 ([`../phase_6/backend/DATABASE_SCHEMA.md`](../../phase_6/backend/DATABASE_SCHEMA.md)).

## New tables

### `ai_classroom_tag` (§18)

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| subject_id | uuid FK → subjects_subject | CASCADE; §18 anchor |
| parent_id | uuid FK → ai_classroom_tag, SET_NULL nullable | hierarchy anchor |
| stable_key | varchar(64) | identity component |
| display_name | varchar(120) | mutable without identity change |
| created_at | timestamptz | |

Constraint: `uniq_tag_subject_stable_key UNIQUE (subject_id, stable_key)` (§66).

### `ai_classroom_documenttag`

document FK CASCADE · tag FK CASCADE · generation_job FK SET_NULL nullable · created_at. Unique(document, tag).

### `ai_classroom_tagchangelog`

id · tag FK **SET_NULL** + `stable_key_snapshot` varchar(64) (log survives deletion) · change_type added/renamed/removed/linked · old_value/new_value blank-able · generation_job FK SET_NULL · created_at.

### `questions_question` (§17/§54)

id uuid PK · document FK CASCADE · source_revision_id uuid · source_chunk_id uuid · difficulty easy/medium/hard · prompt text · options JSONB (list) · answer_index int ≥ 0 · content_hash varchar(64) · question_key varchar(64) · generation_model · prompt_version · stale bool · created_at.
Constraint: `uniq_question_revision_hash_key UNIQUE (source_revision_id, content_hash, question_key)` (§66).
Plus `questions_questiontaglink`: question OneToOne ↔ tag SET_NULL nullable.

### `tests_testinstance` / `tests_testquestion` / `tests_testattempt` (§17)

Instance: profile FK CASCADE · subject SET_NULL nullable · type practice/mock · scheduled_date nullable.
TestQuestion: test FK CASCADE · question FK CASCADE · order — unique(test, question).
Attempt: test FK CASCADE · question FK CASCADE · selected_index ≥ 0 · correct bool · confidence float 0–1 nullable · answered_at auto — unique(test, question).

### `tests_masteryscore` (§18)

profile FK CASCADE · subject SET_NULL nullable · tag FK CASCADE · mastery float 0..1 EMA · attempt_count · correct_count · last_assessed_at nullable.
Unique(profile, tag). Absence ⇒ not_assessed.

### `chat_chatsession` / `chat_chatmessage` (§16)

Session: profile FK CASCADE · subject SET_NULL nullable · title · created_at.
Message: session FK CASCADE related messages · role user/assistant · content text · citations JSONB (refs + verification verdicts) · model · prompt_version · created_at.

### `revision_revisiongoal` (§58)

profile FK CASCADE · subject SET_NULL nullable · target_date date · hours_per_week float nullable · created_at.

## RLS added (Phase 7 bundle `tests/0002_phase7_rls.py`)

Direct profile match: tests_testinstance · tests_masteryscore · chat_chatsession · revision_revisiongoal.
EXISTS chains: ai_classroom_tag (subject→profile) · ai_classroom_documenttag (document) · ai_classroom_tagchangelog (tag→subject) · questions_question (document) · tests_testattempt (test→profile) · chat_chatmessage (session→profile).

## Deviations

1. QuestionTagLink OneToOne: one concept tag per question (multi-tag scoring deferred).
2. TagChangeLog.tag SET_NULL with key snapshot so history survives tag deletion.
