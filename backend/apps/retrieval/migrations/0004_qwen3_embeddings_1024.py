"""Migration: Upgrade embedding column to vector(1024) for Qwen3-Embedding-0.6B.

Phase 3 of StudyAI Phased AI Stack Migration:
- Drops the HNSW index on retrieval_notechunk.embedding.
- Marks any existing 384-d embeddings as stale and nullifies the vector (since pgvector cannot cast vector(384) to vector(1024)).
- Alters the column type to vector(1024).
- Recreates the HNSW index with vector_cosine_ops for 1024-d embeddings.
"""
from django.db import migrations
import apps.retrieval.models


def forward_pre(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS idx_notechunk_hnsw_embedding;")
        cursor.execute(
            "UPDATE retrieval_notechunk SET embedding = NULL, stale = TRUE WHERE embedding IS NOT NULL;"
        )


def forward_post(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notechunk_hnsw_embedding "
            "ON retrieval_notechunk USING hnsw (embedding vector_cosine_ops);"
        )


def backward_pre(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS idx_notechunk_hnsw_embedding;")
        cursor.execute(
            "UPDATE retrieval_notechunk SET embedding = NULL, stale = TRUE WHERE embedding IS NOT NULL;"
        )


def backward_post(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notechunk_hnsw_embedding "
            "ON retrieval_notechunk USING hnsw (embedding vector_cosine_ops);"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("retrieval", "0003_enable_rls"),
    ]

    operations = [
        migrations.RunPython(forward_pre, backward_post),
        migrations.AlterField(
            model_name="notechunk",
            name="embedding",
            field=apps.retrieval.models.AdaptiveVectorField(
                blank=True, dimensions=1024, null=True
            ),
        ),
        migrations.RunPython(forward_post, backward_pre),
    ]
