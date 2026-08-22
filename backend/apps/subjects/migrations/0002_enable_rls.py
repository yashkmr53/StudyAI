"""Enable PostgreSQL RLS on profile-scoped tables (architecture §3).

Policies compare `profile_id` against the transaction-local GUC
`app.current_profile_id`, which application code and Celery workers set
with SET LOCAL inside each transaction. On SQLite (unit-test settings)
this migration is a no-op.
"""
from django.db import migrations

PROFILE_SCOPED_TABLES = [
    ("profiles_profile", "id"),
    ("subjects_subject", "profile_id"),
]


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, column in PROFILE_SCOPED_TABLES:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            cursor.execute(
                f"""
                CREATE POLICY profile_isolation_{table} ON "{table}"
                USING ({column}::text = current_setting('app.current_profile_id', true));
                """
            )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, _ in PROFILE_SCOPED_TABLES:
            cursor.execute(f'DROP POLICY IF EXISTS profile_isolation_{table} ON "{table}";')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("subjects", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
