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
                "required": ["topic", "why_missing", "missing_from_note", "evidence_in_reference", "source_chunk_ids"],
                "properties": {
                    "topic": {"type": "string", "description": "Concise name of the missing concept"},
                    "why_missing": {"type": "string", "description": "Why this concept is necessary for understanding the note"},
                    "missing_from_note": {"type": "string", "description": "What aspect is absent or underdeveloped in the user's note"},
                    "evidence_in_reference": {"type": "string", "description": "Quote or summary from reference supporting this gap"},
                    "source_chunk_ids": {"type": "array", "items": {"type": "string"}, "description": "Reference chunk IDs supporting this gap"},
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
        "output_schema_version": "v2",
        "template": (
            "You are analyzing a student's study note against reference material.\n\n"
            "TASK: Identify MISSING CONCEPTS that are:\n"
            "  1. Present or inferable from the reference material\n"
            "  2. RELEVANT to understanding the user's note\n"
            "  3. MISSING or MATERIALLY UNDERDEVELOPED in the user's note\n\n"
            "CRITICAL RULES:\n"
            "  - A 'topic' must be a MEANINGFUL CONCEPT or PRINCIPLE, not a single word or token\n"
            "  - GOOD topics: 'time complexity', 'proof of correctness', 'amortized analysis', 'chain rule', 'vector nature of force'\n"
            "  - BAD topics: 'binary', 'choice', 'distribute', 'common', 'means', 'individual', 'frames', 'branching', 'deletion', 'derivatives', 'differentiation', 'chain', 'applications'\n"
            "  - DO NOT list topics merely because they appear in the reference\n"
            "  - DO NOT generate generic 'further reading' suggestions\n"
            "  - DO NOT mark information as missing if the note already covers it adequately\n\n"
            "For each genuine gap, provide ALL of these fields:\n"
            "  - topic: MEANINGFUL CONCEPT NAME (e.g., 'time complexity', not 'binary')\n"
            "  - why_missing: why this CONCEPT is necessary for understanding the note\n"
            "  - missing_from_note: what aspect is absent or underdeveloped in the note\n"
            "  - evidence_in_reference: quote or summary from reference supporting this gap\n"
            "  - source_chunk_ids: array of reference chunk IDs that contain the evidence\n\n"
            "EXAMPLES:\n\n"
            "Example 1:\n"
            "User note: \"Dijkstra's algorithm finds the shortest path using a priority queue.\"\n"
            "Reference: \"Dijkstra's algorithm time complexity is O((V+E)log V). Proof uses greedy choice property.\"\n"
            "Correct gaps:\n"
            "  - topic: \"time complexity\"\n"
            "    why_missing: \"Note describes algorithm behavior but not its efficiency\"\n"
            "    missing_from_note: \"No mention of runtime or performance\"\n"
            "    evidence_in_reference: \"Dijkstra's algorithm time complexity is O((V+E)log V)\"\n"
            "    source_chunk_ids: [\"chunk-1\"]\n"
            "  - topic: \"proof of correctness\"\n"
            "    why_missing: \"Understanding why algorithm works requires the proof\"\n"
            "    missing_from_note: \"Note states what algorithm does, not why it's correct\"\n"
            "    evidence_in_reference: \"Proof uses greedy choice property...\"\n"
            "    source_chunk_ids: [\"chunk-2\"]\n\n"
            "Example 2:\n"
            "User note: \"F = ma explains acceleration from force.\"\n"
            "Reference: \"Force and acceleration are vectors. Net force is vector sum. Law holds in inertial frames. F = dp/dt.\"\n"
            "Correct gaps:\n"
            "  - topic: \"vector nature of force and acceleration\"\n"
            "    why_missing: \"F=ma is a vector equation; direction matters\"\n"
            "    missing_from_note: \"Note treats F=ma as scalar\"\n"
            "    evidence_in_reference: \"Force and acceleration are vectors...\"\n"
            "    source_chunk_ids: [\"chunk-1\"]\n"
            "  - topic: \"inertial reference frames\"\n"
            "    why_missing: \"Second law only valid in inertial frames\"\n"
            "    missing_from_note: \"No mention of frame of reference\"\n"
            "    evidence_in_reference: \"Law holds only in inertial reference frames\"\n"
            "    source_chunk_ids: [\"chunk-3\"]\n\n"
            "CRITICAL: Respond with ONLY valid JSON. No other text, no markdown, no explanation.\n"
            'Output: {"gaps": [{"topic": "...", "why_missing": "...", "missing_from_note": "...", "evidence_in_reference": "...", "source_chunk_ids": ["..."]}]}'
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
