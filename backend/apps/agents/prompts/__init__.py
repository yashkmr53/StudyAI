"""Agent Prompts Package (Phase 1)."""
from apps.agents.prompts.agent_prompts import (
    AGENT_SYSTEM_PROMPT,
    TOOL_DESCRIPTION_TEMPLATE,
    build_agent_system_prompt,
)

__all__ = [
    "AGENT_SYSTEM_PROMPT",
    "TOOL_DESCRIPTION_TEMPLATE",
    "build_agent_system_prompt",
]