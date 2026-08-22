"""Enable PostgreSQL RLS on canvas tables (architecture §3).

canvas_canvassession scopes directly on profile_id. Pages and strokes scope
through an EXISTS chain to their session's profile. No-op on SQLite.
"""
from django.db import migrations

STATEMENTS = [
    # (table, enable, policy SQL)
    (
        "canvas_canvassession",
        """
        CREATE POLICY profile_isolation_canvas_canvassession ON canvas_canvassession
        USING (profile_id::text = current_setting('app.current_profile_id', true));
        """,
    ),
    (
        "canvas_canvaspage",
        """
        CREATE POLICY profile_isolation_canvas_canvaspage ON canvas_canvaspage
        USING (
            EXISTS (
                SELECT 1 FROM canvas_canvassession s
                WHERE s.id = session_id
                  AND s.profile_id::text = current_setting('app.current_profile_id', true)
            )
        );
        """,
    ),
    (
        "canvas_canvasstroke",
        """
        CREATE POLICY profile_isolation_canvas_canvasstroke ON canvas_canvasstroke
        USING (
            EXISTS (
                SELECT 1
                FROM canvas_canvaspage p
                JOIN canvas_canvassession s ON s.id = p.session_id
                WHERE p.id = page_id
                  AND s.profile_id::text = current_setting('app.current_profile_id', true)
            )
        );
        """,
    ),
]


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, policy in STATEMENTS:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            cursor.execute(policy)


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, _ in STATEMENTS:
            cursor.execute(f"DROP POLICY IF EXISTS profile_isolation_{table} ON \"{table}\";")
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("canvas", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
