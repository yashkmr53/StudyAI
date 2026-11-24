"""HNSW pgvector cosine index on ReferenceChunk.embedding (T6).

Mirrors apps/retrieval/migrations/0002_vector_indexes.py:
PostgreSQL-only DDL guarded so SQLite tests no-op cleanly.
"""
from django.db import migrations

DDL = [
    "CREATE INDEX IF NOT EXISTS idx_refchunk_hnsw_embedding ON references_referencechunk USING hnsw (embedding vector_cosine_ops);",
]
REVERSE = ["DROP INDEX IF EXISTS idx_refchunk_hnsw_embedding;"]


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
        for statement in REVERSE:
            cursor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0003_enable_rls"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
