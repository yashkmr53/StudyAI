"""Prompt template registry with version management.

Migrates and extends the existing PromptTemplate system from ai_classroom/prompts.py
to work with LangChain's PromptTemplate while preserving version tracking.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from pathlib import Path

from providers.base import Prompt

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


@dataclass
class PromptTemplate:
    """Versioned prompt template with schema validation."""
    name: str
    version: str
    template: str
    output_schema: Optional[Dict[str, Any]] = None
    output_schema_version: str = "v1"
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def format(self, **kwargs) -> str:
        """Format the template with provided variables."""
        return self.template.format(**kwargs)

    def to_langchain(self):
        """Convert to LangChain PromptTemplate."""
        from langchain_core.prompts import PromptTemplate as LCPromptTemplate
        return LCPromptTemplate.from_template(self.template)

    def to_chat_prompt(self):
        """Convert to LangChain ChatPromptTemplate."""
        from langchain_core.prompts import ChatPromptTemplate
        return ChatPromptTemplate.from_template(self.template)


class PromptRegistry:
    """Registry for versioned prompt templates."""

    def __init__(self):
        self._prompts: Dict[str, PromptTemplate] = {}
        self._load_builtin_prompts()

    def _load_builtin_prompts(self):
        """Load prompts from the prompts directory."""
        if not PROMPTS_DIR.exists():
            return

        for prompt_file in PROMPTS_DIR.glob("*.json"):
            try:
                with open(prompt_file) as f:
                    data = json.load(f)
                prompt = PromptTemplate(**data)
                self.register(prompt)
            except Exception as e:
                logger.warning("Failed to load prompt from %s: %s", prompt_file, e)

    def register(self, prompt: PromptTemplate) -> None:
        """Register a prompt template."""
        key = f"{prompt.name}:{prompt.version}"
        if key in self._prompts:
            logger.warning("Overwriting existing prompt: %s", key)
        self._prompts[key] = prompt
        logger.debug("Registered prompt: %s", key)

    def get(self, name: str, version: str = "latest") -> Optional[PromptTemplate]:
        """Get a prompt template by name and version.

        Args:
            name: Prompt name
            version: Specific version or "latest"

        Returns:
            PromptTemplate or None if not found
        """
        if version == "latest":
            # Find highest version for this name
            candidates = [p for k, p in self._prompts.items() if k.startswith(f"{name}:")]
            if not candidates:
                return None
            # Simple version sorting (assumes semantic versioning)
            return max(candidates, key=lambda p: p.version)

        key = f"{name}:{version}"
        return self._prompts.get(key)

    def get_active(self, name: str) -> PromptTemplate:
        """Get the active (latest) version of a prompt.

        Raises:
            KeyError: If prompt not found
        """
        prompt = self.get(name, "latest")
        if prompt is None:
            raise KeyError(f"Prompt not found: {name}")
        return prompt

    def list_prompts(self) -> List[PromptTemplate]:
        """List all registered prompts."""
        return list(self._prompts.values())

    def to_provider_prompt(self, name: str, version: str = "latest", **format_kwargs) -> Prompt:
        """Convert a registered prompt to a provider Prompt dataclass.

        Args:
            name: Prompt name
            version: Version or "latest"
            **format_kwargs: Variables to format into the template

        Returns:
            Prompt dataclass for provider consumption
        """
        template = self.get_active(name) if version == "latest" else self.get(name, version)
        if template is None:
            raise KeyError(f"Prompt not found: {name}:{version}")

        formatted = template.format(**format_kwargs) if format_kwargs else template.template

        return Prompt(
            name=template.name,
            version=template.version,
            system="",  # System prompt handled separately
            user=formatted,
        )


# Global registry instance
_registry = PromptRegistry()


def get_prompt_registry() -> PromptRegistry:
    """Get the global prompt registry."""
    return _registry


def active_prompt(name: str) -> PromptTemplate:
    """Get the active (latest) version of a prompt.

    Maintains compatibility with ai_classroom.prompts.active_prompt()
    """
    return _registry.get_active(name)


def get_prompt(name: str, version: str = "latest") -> Optional[PromptTemplate]:
    """Get a specific prompt version."""
    return _registry.get(name, version)


def validate_stage_output(stage_name: str, data: dict) -> None:
    """Validate stage output against registered schema.

    Maintains compatibility with ai_classroom.prompts.validate_stage_output()
    """
    prompt = _registry.get(stage_name, "latest")
    if prompt is None or prompt.output_schema is None:
        return  # No schema to validate against

    import jsonschema
    try:
        jsonschema.validate(instance=data, schema=prompt.output_schema)
    except jsonschema.ValidationError as e:
        logger.error("Stage output validation failed for %s: %s", stage_name, e)
        raise ValueError(f"Stage {stage_name} output validation failed: {e.message}")


# Convenience function for creating provider Prompt from registry
def build_provider_prompt(
    name: str,
    version: str = "latest",
    system: str = "",
    **format_kwargs,
) -> Prompt:
    """Build a provider Prompt from registry template.

    Args:
        name: Prompt name
        version: Version or "latest"
        system: Optional system prompt
        **format_kwargs: Variables to format into template

    Returns:
        Prompt dataclass ready for provider
    """
    template = _registry.get(name, version) if version != "latest" else _registry.get_active(name)
    if template is None:
        raise KeyError(f"Prompt not found: {name}:{version}")

    user_content = template.format(**format_kwargs) if format_kwargs else template.template

    return Prompt(
        name=template.name,
        version=template.version,
        system=system,
        user=user_content,
    )