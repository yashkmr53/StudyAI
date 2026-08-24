"""Agent execution audit trail and prompt versioning (Phase 1).

AgentExecutionLog: Full trace of every agent execution for observability.
AgentPromptVersion: Versioned system prompts for the agent orchestrator.
"""
import uuid

from django.conf import settings
from django.db import models

from apps.profiles.models import Profile


class AgentExecutionLog(models.Model):
    """Audit trail for every agent execution."""

    class Outcome(models.TextChoices):
        SUCCESS = "success", "success"
        PARTIAL = "partial", "partial"
        FAILED = "failed", "failed"
        LIMIT_REACHED = "limit_reached", "limit_reached"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.CharField(max_length=64, db_index=True)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="agent_executions")
    intent_category = models.CharField(max_length=32)
    model_provider = models.CharField(max_length=64)
    model_name = models.CharField(max_length=128)
    prompt_version = models.CharField(max_length=64)
    tool_call_sequence = models.JSONField(default=list)
    iterations = models.PositiveIntegerField(default=0)
    retrieved_evidence_ids = models.JSONField(default=list)
    total_tokens = models.PositiveIntegerField(default=0)
    total_latency_ms = models.PositiveIntegerField(default=0)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    citation_verification_status = models.CharField(max_length=24, null=True, blank=True)
    guardrail_violations = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("profile", "created_at")),
            models.Index(fields=("request_id",)),
        ]

    def __str__(self) -> str:
        return f"agent_exec {self.request_id} ({self.outcome})"


class AgentPromptVersion(models.Model):
    """Versioned agent system prompts (mirrors PromptVersion pattern)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=64)
    version = models.CharField(max_length=16)
    system_template = models.TextField()
    tool_descriptions = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name", "-version")
        constraints = [
            models.UniqueConstraint(fields=("name", "version"), name="uniq_agent_prompt_name_version"),
        ]

    @property
    def qualified_name(self) -> str:
        return f"{self.name}:{self.version}"

    def __str__(self) -> str:
        return self.qualified_name


def seed_agent_prompt_versions() -> int:
    """Idempotent registry seeding for agent prompts."""
    from django.conf import settings

    from apps.agents.prompts.agent_prompts import AGENT_SYSTEM_PROMPT, TOOL_DESCRIPTION_TEMPLATE
    from apps.agents.tools import get_tool_registry

    model = getattr(settings, "ENRICHMENT_MODEL", "mock-gpt")
    registry = get_tool_registry()

    tool_descriptions = {}
    for tool in registry.list_tools():
        tool_descriptions[tool.metadata.name] = {
            "description": tool.metadata.description,
            "input_schema": tool.metadata.input_schema.model_json_schema(),
            "output_schema": tool.metadata.output_schema.model_json_schema(),
        }

    _, created = AgentPromptVersion.objects.get_or_create(
        name="agent_orchestrator",
        version="v1",
        defaults={
            "system_template": AGENT_SYSTEM_PROMPT,
            "tool_descriptions": tool_descriptions,
            "model": model,
            "is_active": True,
        },
    )
    return 1 if created else 0