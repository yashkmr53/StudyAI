"""RLS on retrieval_notechunk (architecture §3).

User-owned chunks match the transaction-local profile; platform reference
chunks (profile IS NULL) are visible to all authenticated contexts.
Fail-closed for user rows when the GUC is unset. No-op on SQLite.
"""
from django.db import migrations

TABLE = "retrieval_notechunk"
POLICY_NAME = "profile_isolation_retrieval_notechunk"
POLICY = (
    f"CREATE POLICY {POLICY_NAME} ON {TABLE} USING ("
    "profile_id::text = current_setting('app.current_profile_id', true) "
    "OR profile_id IS NULL);"
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
        ("retrieval", "0002_vector_indexes"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
