"""Enable PostgreSQL RLS on canonical document tables (architecture §3).

documents_document scopes directly on profile_id; pages/revisions/lines
scope through EXISTS chains to their document's profile. No-op on SQLite.
"""
from django.db import migrations

POLICIES = [
    (
        "documents_document",
        "CREATE POLICY profile_isolation_documents_document ON documents_document "
        "USING (profile_id::text = current_setting('app.current_profile_id', true));",
    ),
    (
        "documents_documentpage",
        "CREATE POLICY profile_isolation_documents_page ON documents_documentpage "
        "USING (EXISTS (SELECT 1 FROM documents_document d WHERE d.id = document_id "
        "AND d.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
    (
        "documents_documentpagerevision",
        "CREATE POLICY profile_isolation_documents_revision ON documents_documentpagerevision "
        "USING (EXISTS (SELECT 1 FROM documents_documentpage p JOIN documents_document d ON d.id = p.document_id "
        "WHERE p.id = page_id AND d.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
    (
        "documents_documentline",
        "CREATE POLICY profile_isolation_documents_line ON documents_documentline "
        "USING (EXISTS (SELECT 1 FROM documents_documentpagerevision r "
        "JOIN documents_documentpage p ON p.id = r.page_id "
        "JOIN documents_document d ON d.id = p.document_id "
        "WHERE r.id = page_revision_id AND d.profile_id::text = current_setting('app.current_profile_id', true)));",
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
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
