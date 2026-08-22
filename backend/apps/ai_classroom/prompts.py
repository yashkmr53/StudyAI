"""Prompt registry seeding + stage JSON schemas (architecture §11, §13).

Every generation stores prompt_name:version, output schema version,
provider and model. Schemas are validated with jsonschema after each
LLM (mock) call — every node from Draft onward is schema-checked.
"""
import jsonschema
from django.conf import settings

from apps.ai_classroom.models import PromptVersion
from shared.exceptions import ValidationError

# ---------------------------------------------------------------- schemas

DRAFT_SCHEMA = {
    "type": "object",
    "required": ["blocks"],
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["block_type", "content", "generation_method", "source_chunk_ids"],
                "properties": {
                    "block_type": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "generation_method": {"enum": ["llm", "rule_based", "user_edited", "transcribed"]},
                    "source_chunk_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}

GAPS_SCHEMA = {
    "type": "object",
    "required": ["gaps"],
    "properties": {
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["topic", "reference_chunk_id"],
                "properties": {
                    "topic": {"type": "string"},
                    "reference_chunk_id": {"type": "string"},
                },
            },
        }
    },
}

SCHEMAS = {
    "enrichment_draft": DRAFT_SCHEMA,
    "gap_detection": GAPS_SCHEMA,
    "gap_filling": DRAFT_SCHEMA,  # same block shape; blocks cite reference chunks
}


def validate_stage_output(prompt_name: str, data) -> None:
    schema = SCHEMAS.get(prompt_name)
    if schema is None:
        raise ValidationError(f"No schema registered for stage '{prompt_name}'.")
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        raise ValidationError(
            f"Stage output failed schema validation for '{prompt_name}'.",
            details={"reason": exc.message, "path": list(exc.absolute_path)},
        )


# ---------------------------------------------------------------- prompts

DEFAULT_PROMPTS = [
    {
        "prompt_name": "enrichment_draft",
        "version": "v1",
        "output_schema_version": "v1",
        "template": (
            "Draft a structured enrichment grounded ONLY in the provided evidence.\n"
            "Evidence JSON follows. Produce blocks with block_type/title/content,\n"
            "generation_method and source_chunk_ids referencing the evidence ids."
        ),
        "configuration": {"temperature": 0},
    },
    {
        "prompt_name": "gap_detection",
        "version": "v1",
        "output_schema_version": "v1",
        "template": (
            "Compare user-note coverage against reference coverage. Report topics\n"
            "present in references but missing from user notes as gaps."
        ),
        "configuration": {"temperature": 0},
    },
    {
        "prompt_name": "gap_filling",
        "version": "v1",
        "output_schema_version": "v1",
        "template": (
            "Fill each gap using ONLY the cited reference chunk. Mark blocks\n"
            'with block_type="gap_fill" and cite the reference chunk id.'
        ),
        "configuration": {"temperature": 0},
    },
]

QUALIFIED = {p["prompt_name"]: f"{p['prompt_name']}:{p['version']}" for p in DEFAULT_PROMPTS}


def seed_prompt_versions() -> int:
    """Idempotent registry seeding; returns number of rows created."""
    created = 0
    model = getattr(settings, "ENRICHMENT_MODEL", "mock-gpt")
    for spec in DEFAULT_PROMPTS:
        _, was_created = PromptVersion.objects.get_or_create(
            prompt_name=spec["prompt_name"],
            version=spec["version"],
            defaults={
                "template": spec["template"],
                "output_schema_version": spec["output_schema_version"],
                "model": model,
                "configuration": spec.get("configuration", {}),
                "is_active": True,
            },
        )
        created += 1 if was_created else 0
    return created


def active_prompt(prompt_name: str) -> PromptVersion:
    prompt = PromptVersion.objects.filter(prompt_name=prompt_name, is_active=True).first()
    if prompt is None:
        seed_prompt_versions()
        prompt = PromptVersion.objects.get(prompt_name=prompt_name, version="v1")
    return prompt
