"""Enable PostgreSQL RLS on documents_digitizeddocument (architecture §3).

Scopes through an EXISTS chain to the document's profile. No-op on SQLite.
"""
from django.db import migrations

TABLE = "documents_digitizeddocument"
POLICY_NAME = "profile_isolation_documents_digitized"
POLICY = (
    f"CREATE POLICY {POLICY_NAME} ON {TABLE} "
    "USING (EXISTS (SELECT 1 FROM documents_document d WHERE d.id = document_id "
    "AND d.profile_id::text = current_setting('app.current_profile_id', true)));"
)


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY;')
        cursor.execute(POLICY)


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{TABLE}";')
        cursor.execute(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0003_documentline_is_heading_digitizeddocument"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
