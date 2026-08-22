from rest_framework import serializers

from apps.questions.models import Question


class QuestionSerializer(serializers.ModelSerializer):
    answer_text = serializers.CharField(read_only=True)

    class Meta:
        model = Question
        fields = (
            "id",
            "document",
            "source_revision_id",
            "source_chunk_id",
            "difficulty",
            "prompt",
            "options",
            "answer_index",
            "answer_text",
            "content_hash",
            "question_key",
            "generation_model",
            "prompt_version",
            "stale",
            "created_at",
        )