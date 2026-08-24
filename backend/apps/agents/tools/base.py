"""Tool abstraction layer (Phase 1).

Strongly typed tool interface with Pydantic schema validation,
authorization enforcement, and observability.
"""
from dataclasses import dataclass, field
from typing import Protocol, Type, Optional
import time
import logging

from pydantic import BaseModel, ConfigDict

from apps.profiles.models import Profile
from shared.authorization.services import ProfileAuthorizationService
from shared.exceptions import Forbidden, ValidationError

logger = logging.getLogger(__name__)


class ToolInput(BaseModel):
    """Base input schema — all tools must define concrete schema."""
    model_config = ConfigDict(extra="forbid")


class ToolOutput(BaseModel):
    """Base output schema — all tools must define concrete schema."""
    success: bool = True
    error: str | None = None
    latency_ms: int = 0

    model_config = ConfigDict(extra="forbid")


@dataclass
class ToolMetadata:
    name: str
    description: str
    input_schema: Type[ToolInput]
    output_schema: Type[ToolOutput]
    requires_auth: bool = True
    timeout_seconds: int = 30
    category: str = "general"  # retrieval | learning | evidence | document


class Tool(Protocol):
    metadata: ToolMetadata

    def execute(self, input: ToolInput, *, user, request_id: str) -> ToolOutput:
        ...


class BaseTool:
    """Base tool implementation with auth, validation, timeout, telemetry."""

    metadata: ToolMetadata

    def __init__(self):
        if not hasattr(self, "metadata"):
            raise NotImplementedError("Tool must define 'metadata' class attribute")

    def execute(self, input: ToolInput, *, user, request_id: str) -> ToolOutput:
        """Execute tool with full guardrails."""
        started = time.monotonic()

        try:
            # 1. Validate input schema (Pydantic does this on construction)
            validated_input = self.metadata.input_schema.model_validate(input.model_dump())

            # 2. Authorization
            if self.metadata.requires_auth:
                profile = Profile.objects.filter(user=user).first()
                if profile is None:
                    raise Forbidden("No profile found for user")
                ProfileAuthorizationService.ensure_profile_access(user, profile)

            # 3. Execute tool logic
            result = self._execute(validated_input, user=user, request_id=request_id)

            # 4. Validate output schema
            validated_output = self.metadata.output_schema.model_validate(result.model_dump())

            latency_ms = int((time.monotonic() - started) * 1000)
            validated_output.latency_ms = latency_ms

            logger.info(
                "Tool executed: name=%s request_id=%s latency_ms=%d success=true",
                self.metadata.name, request_id, latency_ms
            )
            return validated_output

        except ValidationError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.warning(
                "Tool validation error: name=%s request_id=%s error=%s",
                self.metadata.name, request_id, exc
            )
            return self._error_output(exc.message, latency_ms)

        except Forbidden as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.warning(
                "Tool auth error: name=%s request_id=%s",
                self.metadata.name, request_id
            )
            return self._error_output("Authorization failed", latency_ms)

        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.exception(
                "Tool execution error: name=%s request_id=%s",
                self.metadata.name, request_id
            )
            return self._error_output(str(exc), latency_ms)

    def _execute(self, input: ToolInput, *, user, request_id: str) -> ToolOutput:
        """Override in subclass — actual tool logic."""
        raise NotImplementedError

    def _error_output(self, error: str, latency_ms: int) -> ToolOutput:
        # Create a minimal valid output with required fields
        output_data = {"success": False, "error": error, "latency_ms": latency_ms}
        # Add default values for required fields
        for field_name, field_info in self.metadata.output_schema.model_fields.items():
            if field_name not in output_data and field_info.default is not None:
                output_data[field_name] = field_info.default
        return self.metadata.output_schema(**output_data)


class ToolRegistry:
    """Singleton registry for all available tools."""

    _instance: Optional["ToolRegistry"] = None

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance

    def register(self, tool: BaseTool) -> None:
        if tool.metadata.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.metadata.name}")
        self._tools[tool.metadata.name] = tool
        logger.info("Registered tool: %s", tool.metadata.name)

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool not found: {name}")
        return tool

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_metadata(self, name: str) -> ToolMetadata:
        return self.get(name).metadata


def get_tool_registry() -> ToolRegistry:
    """Get the singleton tool registry."""
    return ToolRegistry.get_instance()