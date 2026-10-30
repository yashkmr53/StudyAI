# Generated for StudyAI: PR 1 Step 1 - Transcript Schema Nullable

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0008_documentpage_approved_at_documentpage_approved_by_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # DocumentPage fields
        migrations.AddField(
            model_name="documentpage",
            name="is_ignored",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="documentpage",
            name="ocr_attempt_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="documentpage",
            name="ocr_generation",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="documentpage",
            name="ocr_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="documentpage",
            name="index_epoch",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="documentpage",
            name="indexed_text_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        # DocumentPageRevision fields
        migrations.AddField(
            model_name="documentpagerevision",
            name="parent_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="derived_revisions",
                to="documents.documentpagerevision",
            ),
        ),
        migrations.AddField(
            model_name="documentpagerevision",
            name="revision_type",
            field=models.CharField(
                choices=[("ocr", "OCR"), ("user_edit", "User Edit")],
                default="ocr",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="documentpagerevision",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_revisions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="documentpagerevision",
            name="review_reasons",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="documentpagerevision",
            name="text_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        # DocumentLine fields (nullable lineage_id and original_text for batch backfill in 0010)
        migrations.AddField(
            model_name="documentline",
            name="lineage_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="documentline",
            name="original_text",
            field=models.TextField(blank=True, default="", null=True),
        ),
        migrations.AddField(
            model_name="documentline",
            name="is_edited",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="documentline",
            name="is_user_added",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="documentline",
            name="parent_line_id",
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
