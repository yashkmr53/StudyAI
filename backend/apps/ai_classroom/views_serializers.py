"""Serializers for the AI Classroom generated layer (§9/§12 shapes)."""
from rest_framework import serializers

from apps.ai_classroom.models import EnrichedNote
from apps.jobs.models import Job


class EnrichedNoteSerializer(serializers.ModelSerializer):
    blocks = serializers.SerializerMethodField()
    job_status = serializers.SerializerMethodField()

    class Meta:
        model = EnrichedNote
        fields = (
            "id", "document", "revision_ids", "provider", "model",
            "prompt_version", "schema_version", "ai_stale", "blocks",
            "job_status", "created_at",
        )

    def get_blocks(self, obj) -> list:
        out = []
        for block in obj.blocks.order_by("block_index"):
            citation = getattr(block, "citation", None)
            out.append({
                "block_index": block.block_index,
                "block_type": block.block_type,
                "title": block.title,
                "content": block.content,
                "generation_method": block.generation_method,
                "source_chunk_ids": block.source_chunk_ids,
                "citation": (
                    {
                        "source_refs": citation.source_refs,
                        "verification_status": citation.verification_status,
                        "verification_score": citation.verification_score,
                        "verifier_version": citation.verifier_version,
                    }
                    if citation
                    else None
                ),
            })
        return out

    def get_job_status(self, obj) -> str | None:
        job = (
            Job.objects.filter(resource_type="document", resource_id=str(obj.document_id))
            .order_by("-created_at")
            .first()
        )
        return job.status if job else None
