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
            "CRITICAL: You must respond with ONLY valid JSON. No other text, no YAML, no Markdown.\n"
            "Output a JSON object with a 'blocks' array. Each block must have:\n"
            "- block_type (string): one of overview, key_concept, explanation, example, gap_fill\n"
            "- title (string): concise heading\n"
            "- content (string): 1-3 sentences grounded in evidence\n"
            "- generation_method (string): llm, rule_based, user_edited, or transcribed\n"
            "- source_chunk_ids (array of strings): ids from the evidence\n"
            "Evidence JSON follows."
        ),
        "configuration": {"temperature": 0},
    },
    {
        "prompt_name": "gap_detection",
        "version": "v1",
        "output_schema_version": "v1",
        "template": (
            "Compare user-note coverage against reference coverage. Report topics\n"
            "present in references but missing from user notes as gaps.\n"
            "CRITICAL: Respond with ONLY valid JSON. No other text.\n"
            'Output: {"gaps": [{"topic": "...", "reference_chunk_id": "..."}]}'
        ),
        "configuration": {"temperature": 0},
    },
    {
        "prompt_name": "gap_filling",
        "version": "v1",
        "output_schema_version": "v1",
        "template": (
            "Fill each gap using ONLY the cited reference chunk. Mark blocks\n"
            'with block_type="gap_fill" and cite the reference chunk id.\n'
            "CRITICAL: Respond with ONLY valid JSON. No other text.\n"
            "Output: {\"blocks\": [{\"block_type\": \"gap_fill\", \"title\": \"...\", "
            "\"content\": \"...\", \"generation_method\": \"llm\", "
            "\"source_chunk_ids\": [\"...\"]}]}"
        ),
        "configuration": {"temperature": 0},
    },
]

QUALIFIED = {p["prompt_name"]: f"{p['prompt_name']}:{p['version']}" for p in DEFAULT_PROMPTS}


def seed_prompt_versions() -> int:
    """Idempotent registry seeding; returns number of rows created/updated."""
    created = 0
    model = getattr(settings, "ENRICHMENT_MODEL", "mock-gpt")
    for spec in DEFAULT_PROMPTS:
        obj, was_created = PromptVersion.objects.update_or_create(
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
