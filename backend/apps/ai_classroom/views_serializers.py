"""Serializers for the AI Classroom generated layer (§9/§12 shapes)."""
from typing import Optional
from rest_framework import serializers

from apps.ai_classroom.models import EnrichedNote
from apps.jobs.models import Job


class EnrichedNoteSerializer(serializers.ModelSerializer):
    blocks = serializers.SerializerMethodField()
    job_status = serializers.SerializerMethodField()
    reference_library_changed = serializers.SerializerMethodField()
    subject_id = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()

    class Meta:
        model = EnrichedNote
        fields = (
            "id", "document", "status", "content_hash", "force_include_hash",
            "settings_version", "reference_snapshot_hash", "reference_library_changed",
            "subject_id", "subject_name",
            "revision_ids", "evidence_status_by_topic",
            "excluded_segments", "diagnostics", "provider", "model",
            "prompt_version", "schema_version", "ai_stale", "empty_reason",
            "blocks", "job_status", "created_at",
        )

    def get_blocks(self, obj) -> list:
        from django.conf import settings
        show_partial = getattr(settings, "ENRICHMENT_SHOW_PARTIAL", True)
        if isinstance(show_partial, str):
            show_partial = show_partial.lower() in ("1", "true", "yes")

        out = []
        for block in obj.blocks.order_by("block_index"):
            b_kind = getattr(block, "block_kind", "legacy")
            sup_status = getattr(block, "support_status", "")
            if not show_partial and b_kind == "addition" and sup_status == "partial":
                continue

            citation = getattr(block, "citation", None)
            out.append({
                "block_index": block.block_index,
                "block_kind": b_kind,
                "render_as": getattr(block, "render_as", "prose"),
                "topic_id": getattr(block, "topic_id", ""),
                "block_type": block.block_type,
                "title": block.title,
                "content": block.content,
                "source_line_ids": getattr(block, "source_line_ids", []),
                "support_status": sup_status,
                "addition_kind": getattr(block, "addition_kind", ""),
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

    def get_reference_library_changed(self, obj) -> bool:
        """True when reference library changed and note has missing/partial topic (§3.3)."""
        if not obj.document or not obj.reference_snapshot_hash:
            # Blank hash on legacy notes is treated as unknown; do not flag as changed
            return False
        from apps.references.services import reference_library_hash
        current_hash = reference_library_hash(obj.document.subject, profile=obj.document.profile)
        status_vals = (obj.evidence_status_by_topic or {}).values()
        has_gap = any(s in ("none", "partial") for s in status_vals)
        return bool(has_gap and (obj.reference_snapshot_hash != current_hash))

    def get_subject_id(self, obj) -> Optional[str]:
        if obj.document and obj.document.subject_id:
            return str(obj.document.subject_id)
        return None

    def get_subject_name(self, obj) -> Optional[str]:
        if obj.document and obj.document.subject:
            return obj.document.subject.name
        return None

    def get_job_status(self, obj) -> Optional[str]:
        job = (
            Job.objects.filter(resource_type="document", resource_id=str(obj.document_id))
            .order_by("-created_at")
            .first()
        )
        return job.status if job else None
