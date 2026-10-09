"""Phase 12: Security & RLS Hardening (FORCE RLS and application role).

Enforces PostgreSQL FORCE ROW LEVEL SECURITY across all tenant tables,
ensures restricted application role studyai_app exists with required permissions,
and configures profiles_profile for non-locking profile listing.
"""
from django.db import migrations

TENANT_TABLES = [
    "canvas_canvaspage",
    "canvas_canvassession",
    "canvas_canvasstroke",
    "chat_chatmessage",
    "chat_chatsession",
    "documents_digitizeddocument",
    "documents_document",
    "documents_documentline",
    "documents_documentpage",
    "documents_documentpagerevision",
    "notebooks_notebook",
    "notebooks_notebookline",
    "notebooks_notebookpage",
    "questions_question",
    "retrieval_notechunk",
    "revision_revisiongoal",
    "subjects_subject",
    "tests_masteryscore",
    "tests_testattempt",
    "tests_testinstance",
    "ai_classroom_citationblock",
    "ai_classroom_documenttag",
    "ai_classroom_enrichednote",
    "ai_classroom_enrichednoteblock",
    "ai_classroom_tag",
    "ai_classroom_tagchangelog",
]


def apply_rls_hardening(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        # 1. Ensure restricted role studyai_app exists and has permissions
        cursor.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'studyai_app') THEN
                    CREATE ROLE studyai_app WITH LOGIN PASSWORD 'studyai_app_pass' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
                END IF;
            END $$;
            GRANT CONNECT ON DATABASE studyai TO studyai_app;
            GRANT USAGE ON SCHEMA public TO studyai_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO studyai_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO studyai_app;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO studyai_app;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO studyai_app;
            """
        )

        # 2. FORCE ROW LEVEL SECURITY on all tenant tables
        for table in TENANT_TABLES:
            cursor.execute(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT FROM pg_tables WHERE tablename = '{table}') THEN
                        EXECUTE 'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;';
                    END IF;
                END $$;
                """
            )

        # 3. Disable RLS on profiles_profile so application role can query profiles for switcher/picker
        cursor.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'profiles_profile') THEN
                    EXECUTE 'ALTER TABLE "profiles_profile" DISABLE ROW LEVEL SECURITY;';
                END IF;
            END $$;
            """
        )


def revert_rls_hardening(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TENANT_TABLES:
            cursor.execute(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT FROM pg_tables WHERE tablename = '{table}') THEN
                        EXECUTE 'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;';
                    END IF;
                END $$;
                """
            )


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0002_providercalllog_estimated_cost_usd_and_more"),
        ("subjects", "0002_enable_rls"),
        ("tests", "0002_phase7_rls"),
    ]

    operations = [
        migrations.RunPython(apply_rls_hardening, revert_rls_hardening),
    ]
