"""Agent API Serializers (Phase 1)."""
from rest_framework import serializers

from apps.chat.models import ChatSession


class AgentChatRequestSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    content = serializers.CharField(min_length=1, max_length=4000)


class ToolCallSerializer(serializers.Serializer):
    tool = serializers.CharField()
    arguments = serializers.DictField()
    result = serializers.DictField()
    latency_ms = serializers.IntegerField()
    success = serializers.BooleanField()
    error = serializers.CharField(allow_null=True, required=False)


class AgentChatResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    citations = serializers.ListField(child=serializers.DictField())
    tool_calls = ToolCallSerializer(many=True)
    iterations = serializers.IntegerField()
    total_tokens = serializers.IntegerField()
    total_latency_ms = serializers.IntegerField()
    outcome = serializers.CharField()
    trace_id = serializers.CharField()
    verification_status = serializers.CharField(allow_null=True, required=False)
    verification_score = serializers.FloatField(allow_null=True, required=False)


class ToolMetadataSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    input_schema = serializers.DictField()
    output_schema = serializers.DictField()
    requires_auth = serializers.BooleanField()
    timeout_seconds = serializers.IntegerField()


class AgentExecutionLogSerializer(serializers.Serializer):
    request_id = serializers.CharField()
    profile = serializers.UUIDField()
    intent_category = serializers.CharField()
    model_provider = serializers.CharField()
    model_name = serializers.CharField()
    prompt_version = serializers.CharField()
    tool_call_sequence = serializers.ListField(child=serializers.DictField())
    iterations = serializers.IntegerField()
    retrieved_evidence_ids = serializers.ListField(child=serializers.CharField())
    total_tokens = serializers.IntegerField()
    total_latency_ms = serializers.IntegerField()
    outcome = serializers.CharField()
    citation_verification_status = serializers.CharField(allow_null=True)
    guardrail_violations = serializers.IntegerField()
    created_at = serializers.DateTimeField()