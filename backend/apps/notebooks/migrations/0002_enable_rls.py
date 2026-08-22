"""Enable PostgreSQL RLS on notebook tables.

notebooks_notebook scopes directly on profile_id; pages/lines scope through
EXISTS chains to their notebook's profile. No-op on SQLite.
"""
from django.db import migrations

POLICIES = [
    (
        "notebooks_notebook",
        "CREATE POLICY profile_isolation_notebooks_notebook ON notebooks_notebook "
        "USING (profile_id::text = current_setting('app.current_profile_id', true));",
    ),
    (
        "notebooks_notebookpage",
        "CREATE POLICY profile_isolation_notebooks_page ON notebooks_notebookpage "
        "USING (EXISTS (SELECT 1 FROM notebooks_notebook n WHERE n.id = notebook_id "
        "AND n.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
    (
        "notebooks_notebookline",
        "CREATE POLICY profile_isolation_notebooks_line ON notebooks_notebookline "
        "USING (EXISTS (SELECT 1 FROM notebooks_notebookpage p JOIN notebooks_notebook n ON n.id = p.notebook_id "
        "WHERE p.id = page_id AND n.profile_id::text = current_setting('app.current_profile_id', true)));",
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
        ("notebooks", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]