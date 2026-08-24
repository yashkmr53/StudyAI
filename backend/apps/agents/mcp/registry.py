"""MCP Tool Registry (Phase 3).

Maps StudyAI internal tools to MCP tool definitions with JSON Schema.
"""
import json
from typing import Any, Callable
from dataclasses import dataclass, field

from apps.agents.tools import get_tool_registry
from apps.agents.tools.base import BaseTool, ToolMetadata, ToolInput, ToolOutput


@dataclass
class MCPToolDefinition:
    """MCP-compatible tool definition."""
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    requires_auth: bool = True
    category: str = "general"
    # Internal tool reference
    _internal_tool: BaseTool | None = field(default=None, repr=False)

    def to_mcp_dict(self) -> dict:
        """Convert to MCP tool definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
        }


class MCPToolRegistry:
    """Registry that maps StudyAI tools to MCP definitions."""
    
    def __init__(self):
        self._tools: dict[str, MCPToolDefinition] = {}
        self._register_all_tools()
    
    def _register_all_tools(self) -> None:
        """Register all StudyAI tools as MCP tools."""
        internal_registry = get_tool_registry()
        
        for internal_tool in internal_registry.list_tools():
            metadata = internal_tool.metadata
            
            # Convert Pydantic schemas to JSON Schema
            input_schema = metadata.input_schema.model_json_schema()
            output_schema = metadata.output_schema.model_json_schema()
            
            mcp_tool = MCPToolDefinition(
                name=metadata.name,
                description=metadata.description,
                input_schema=input_schema,
                output_schema=output_schema,
                requires_auth=metadata.requires_auth,
                category=metadata.category,
                _internal_tool=internal_tool,
            )
            
            self._tools[metadata.name] = mcp_tool
    
    def list_tools(self) -> list[MCPToolDefinition]:
        """Get all MCP tool definitions."""
        return list(self._tools.values())
    
    def get_tool(self, name: str) -> MCPToolDefinition | None:
        """Get a specific tool by name."""
        return self._tools.get(name)
    
    def get_tool_definitions(self) -> list[dict]:
        """Get tool definitions in MCP format for tools/list."""
        return [tool.to_mcp_dict() for tool in self._tools.values()]
    
    async def call_tool(
        self,
        name: str,
        arguments: dict,
        user_context: "MCPUserContext",
    ) -> dict:
        """Execute a tool via MCP."""
        mcp_tool = self._tools.get(name)
        if not mcp_tool:
            raise ValueError(f"Unknown tool: {name}")
        
        if not mcp_tool._internal_tool:
            raise ValueError(f"Tool {name} has no internal implementation")
        
        internal_tool = mcp_tool._internal_tool
        
        # Validate input
        input_model = internal_tool.metadata.input_schema(**arguments)
        
        # Execute with user context
        result = internal_tool.execute(
            input_model,
            user=user_context.user,
            request_id=user_context.request_id,
        )
        
        return result.model_dump()
    
    def get_tools_by_category(self, category: str) -> list[MCPToolDefinition]:
        """Get tools filtered by category."""
        return [t for t in self._tools.values() if t.category == category]


# Singleton instance
_mcp_registry: MCPToolRegistry | None = None

def get_mcp_tool_registry() -> MCPToolRegistry:
    """Get the singleton MCP tool registry."""
    global _mcp_registry
    if _mcp_registry is None:
        _mcp_registry = MCPToolRegistry()
    return _mcp_registry