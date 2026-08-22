"""RLS on generated-layer tables (architecture §3).

EnrichedNote scopes through its document's profile; blocks/citations
nest one level deeper. No-op on SQLite.
"""
from django.db import migrations

POLICIES = [
    (
        "ai_classroom_enrichednote",
        "CREATE POLICY profile_isolation_enrichednote ON ai_classroom_enrichednote "
        "USING (EXISTS (SELECT 1 FROM documents_document d WHERE d.id = document_id "
        "AND d.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
    (
        "ai_classroom_enrichednoteblock",
        "CREATE POLICY profile_isolation_enrichedblock ON ai_classroom_enrichednoteblock "
        "USING (EXISTS (SELECT 1 FROM ai_classroom_enrichednote n JOIN documents_document d ON d.id = n.document_id "
        "WHERE n.id = enriched_note_id AND d.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
    (
        "ai_classroom_citationblock",
        "CREATE POLICY profile_isolation_enrichedcitation ON ai_classroom_citationblock "
        "USING (EXISTS (SELECT 1 FROM ai_classroom_enrichednoteblock b "
        "JOIN ai_classroom_enrichednote n ON n.id = b.enriched_note_id "
        "JOIN documents_document d ON d.id = n.document_id "
        "WHERE b.id = enriched_note_block_id AND d.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
]


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, policy in POLICIES:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            cursor.execute(policy)


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, policy in POLICIES:
            policy_name = policy.split("ON")[0].split()[-1]
            cursor.execute(f'DROP POLICY IF EXISTS {policy_name} ON "{table}";')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("ai_classroom", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
