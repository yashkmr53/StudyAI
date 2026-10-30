# Generated for StudyAI: PR 1 Step 1 - Transcript Constraints and NOT NULL

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0010_transcript_data_backfill"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentline",
            name="lineage_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4),
        ),
        migrations.AlterField(
            model_name="documentline",
            name="original_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddConstraint(
            model_name="documentline",
            constraint=models.UniqueConstraint(
                fields=("page_revision", "lineage_id"),
                name="uniq_revision_lineage_id",
            ),
        ),
    ]
