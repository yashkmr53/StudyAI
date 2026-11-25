"""MCP Adapter (Phase 3).

Exposes StudyAI tools via the Model Context Protocol (MCP).
"""
from apps.agents.mcp.server import MCPServer, create_mcp_server
from apps.agents.mcp.auth import MCPAuthenticator, MCPTokenValidator
from apps.agents.mcp.client import (
    MCPClient,
    MCPClientError,
    MCPClientToolAdapter,
    discover_mcp_tools,
    register_external_mcp_tools,
)
from apps.agents.mcp.registry import MCPToolRegistry
from apps.agents.mcp.views import MCPHTTPView, MCPTokenView
from apps.agents.mcp.telemetry import record_mcp_call, get_mcp_stats, get_recent_mcp_calls

__all__ = [
    "MCPServer",
    "create_mcp_server",
    "MCPAuthenticator",
    "MCPTokenValidator",
    "MCPClient",
    "MCPClientError",
    "MCPClientToolAdapter",
    "discover_mcp_tools",
    "register_external_mcp_tools",
    "MCPToolRegistry",
    "MCPHTTPView",
    "MCPTokenView",
    "record_mcp_call",
    "get_mcp_stats",
    "get_recent_mcp_calls",
]