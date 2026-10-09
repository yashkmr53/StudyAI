"""Enable PostgreSQL RLS on references tables (Phase 12).

User-owned references match the transaction-local profile; platform global references
(profile IS NULL) are visible to all authenticated contexts.
Fail-closed for private rows when GUC is unset. No-op on SQLite.
"""
from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        # 1. ReferenceDocument RLS
        cursor.execute('ALTER TABLE "references_referencedocument" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('ALTER TABLE "references_referencedocument" FORCE ROW LEVEL SECURITY;')
        cursor.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE tablename = 'references_referencedocument'
                    AND policyname = 'profile_isolation_references_referencedocument'
                ) THEN
                    CREATE POLICY profile_isolation_references_referencedocument
                    ON "references_referencedocument"
                    USING (
                        profile_id::text = current_setting('app.current_profile_id', true)
                        OR profile_id IS NULL
                    );
                END IF;
            END $$;
            """
        )

        # 2. ReferenceChunk RLS
        cursor.execute('ALTER TABLE "references_referencechunk" ENABLE ROW LEVEL SECURITY;')
        cursor.execute('ALTER TABLE "references_referencechunk" FORCE ROW LEVEL SECURITY;')
        cursor.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE tablename = 'references_referencechunk'
                    AND policyname = 'profile_isolation_references_referencechunk'
                ) THEN
                    CREATE POLICY profile_isolation_references_referencechunk
                    ON "references_referencechunk"
                    USING (
                        EXISTS (
                            SELECT 1 FROM references_referencedocument rd
                            WHERE rd.id = references_referencechunk.reference_document_id
                            AND (
                                rd.profile_id::text = current_setting('app.current_profile_id', true)
                                OR rd.profile_id IS NULL
                            )
                        )
                    );
                END IF;
            END $$;
            """
        )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS profile_isolation_references_referencechunk ON "references_referencechunk";')
        cursor.execute('ALTER TABLE "references_referencechunk" NO FORCE ROW LEVEL SECURITY;')
        cursor.execute('ALTER TABLE "references_referencechunk" DISABLE ROW LEVEL SECURITY;')

        cursor.execute('DROP POLICY IF EXISTS profile_isolation_references_referencedocument ON "references_referencedocument";')
        cursor.execute('ALTER TABLE "references_referencedocument" NO FORCE ROW LEVEL SECURITY;')
        cursor.execute('ALTER TABLE "references_referencedocument" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0002_referencedocument_referencechunk_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
