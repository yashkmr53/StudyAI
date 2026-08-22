"""Create the pgvector extension before any vector columns exist.

Runs first for the retrieval app (run_before 0001) so fresh databases
(including test databases) have `vector` available when NoteChunk is
created. Requires appropriate privileges; PostgreSQL-only.
"""
from django.db import migrations


def forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")


def backward(apps, schema_editor):
    # Never drop the extension automatically — other objects may rely on it.
    pass


class Migration(migrations.Migration):
    dependencies = []

    run_before = [
        ("retrieval", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
