# Generated migration for AgentExecutionLog and AgentPromptVersion
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("profiles", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentExecutionLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("request_id", models.CharField(max_length=64, db_index=True)),
                ("intent_category", models.CharField(max_length=32)),
                ("model_provider", models.CharField(max_length=64)),
                ("model_name", models.CharField(max_length=128)),
                ("prompt_version", models.CharField(max_length=64)),
                ("tool_call_sequence", models.JSONField(default=list)),
                ("iterations", models.PositiveIntegerField(default=0)),
                ("retrieved_evidence_ids", models.JSONField(default=list)),
                ("total_tokens", models.PositiveIntegerField(default=0)),
                ("total_latency_ms", models.PositiveIntegerField(default=0)),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("success", "success"),
                            ("partial", "partial"),
                            ("failed", "failed"),
                            ("limit_reached", "limit_reached"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "citation_verification_status",
                    models.CharField(blank=True, max_length=24, null=True),
                ),
                ("guardrail_violations", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_executions",
                        to="profiles.profile",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="AgentPromptVersion",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=64)),
                ("version", models.CharField(max_length=16)),
                ("system_template", models.TextField()),
                ("tool_descriptions", models.JSONField(default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ("name", "-version"),
            },
        ),
        migrations.AddConstraint(
            model_name="agentpromptversion",
            constraint=models.UniqueConstraint(
                fields=("name", "version"), name="uniq_agent_prompt_name_version"
            ),
        ),
        migrations.AddIndex(
            model_name="agentexecutionlog",
            index=models.Index(fields=["profile", "created_at"], name="agents_agent_profile_crea_123456_idx"),
        ),
        migrations.AddIndex(
            model_name="agentexecutionlog",
            index=models.Index(fields=["request_id"], name="agents_agent_request_123456_idx"),
        ),
    ]