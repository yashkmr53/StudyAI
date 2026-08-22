"""pgvector extension, HNSW + GIN indexes (architecture §32/§33).

Extension creation requires appropriate DB privileges in production
(superuser or the extension being pre-installed/trusted). Index DDL is
PostgreSQL-only and no-ops elsewhere.
"""
from django.db import migrations

DDL = [
    "CREATE EXTENSION IF NOT EXISTS vector;",
    "CREATE INDEX IF NOT EXISTS idx_notechunk_hnsw_embedding ON retrieval_notechunk USING hnsw (embedding vector_cosine_ops);",
]
REVERSE = ["DROP INDEX IF EXISTS idx_notechunk_hnsw_embedding;"]


def forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for statement in DDL:
            cursor.execute(statement)


def backward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(REVERSE[0])


class Migration(migrations.Migration):
    dependencies = [
        ("retrieval", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
