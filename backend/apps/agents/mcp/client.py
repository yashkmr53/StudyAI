"""Outbound MCP JSON-RPC 2.0 client and BaseTool adapter (R8).

Allows StudyAI's agentic ToolRegistry to discover and invoke tools exposed by
external Model Context Protocol servers while preserving StudyAI profile
authorization, schema validation, and telemetry.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional
from uuid import uuid4

import requests
from pydantic import ConfigDict, Field

from apps.agents.mcp.telemetry import record_mcp_call
from apps.agents.tools.base import BaseTool, ToolInput, ToolMetadata, ToolOutput, get_tool_registry

logger = logging.getLogger(__name__)


class MCPClientError(RuntimeError):
    """Raised when an outbound MCP JSON-RPC request fails."""


class MCPClientToolInput(ToolInput):
    """Flexible input schema permitting tool-specific arguments for external MCP tools."""

    model_config = ConfigDict(extra="allow")


class MCPClientToolOutput(ToolOutput):
    """Standardized output envelope returned by MCPClientToolAdapter."""

    result: dict[str, Any] = Field(default_factory=dict)
    content: list[dict[str, Any]] = Field(default_factory=list)


class MCPClient:
    """Lightweight HTTP JSON-RPC 2.0 client for external MCP servers."""

    def __init__(
        self,
        endpoint_url: str,
        *,
        auth_token: Optional[str] = None,
        timeout: float = 30.0,
        transport: Optional[Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]] = None,
    ):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self._transport = transport or self._http_post

    def _http_post(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def rpc(self, method: str, params: Optional[dict[str, Any]] = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": uuid4().hex,
            "method": method,
            "params": params or {},
        }
        try:
            body = self._transport(self.endpoint_url, payload, self._headers())
        except Exception as exc:  # noqa: BLE001
            raise MCPClientError(f"MCP transport failure for {method}: {exc}") from exc

        if not isinstance(body, dict):
            raise MCPClientError(f"Invalid MCP response envelope for {method}")
        if body.get("error"):
            err = body["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise MCPClientError(f"MCP error on {method}: {msg}")
        return body.get("result")

    def initialize(self, *, protocol_version: str = "2024-11-05") -> dict[str, Any]:
        return self.rpc("initialize", {"protocolVersion": protocol_version}) or {}

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.rpc("tools/list") or {}
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return [t for t in tools if isinstance(t, dict) and t.get("name")]

    def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        result = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return result if isinstance(result, dict) else {"value": result}


class MCPClientToolAdapter(BaseTool):
    """Wraps a remote MCP tool as a StudyAI BaseTool for ToolRegistry orchestration."""

    def __init__(
        self,
        client: MCPClient,
        *,
        tool_name: str,
        description: str = "",
        input_schema_spec: Optional[dict[str, Any]] = None,
        requires_auth: bool = True,
        category: str = "external_mcp",
    ):
        self._client = client
        self.input_schema_spec = input_schema_spec or {"type": "object"}
        self.metadata = ToolMetadata(
            name=tool_name,
            description=description or f"External MCP tool '{tool_name}'",
            input_schema=MCPClientToolInput,
            output_schema=MCPClientToolOutput,
            requires_auth=requires_auth,
            timeout_seconds=int(client.timeout),
            category=category,
        )
        super().__init__()

    def _execute(self, input: ToolInput, *, user, request_id: str) -> MCPClientToolOutput:
        arguments = input.model_dump()
        started = time.monotonic()
        raw = self._client.call_tool(self.metadata.name, arguments)
        latency_ms = int((time.monotonic() - started) * 1000)

        content = raw.get("content", []) if isinstance(raw.get("content"), list) else []
        record_mcp_call(
            tool_name=self.metadata.name,
            client_id=f"outbound:{self._client.endpoint_url}",
            user_id=getattr(user, "pk", None),
            request_id=request_id,
            latency_ms=latency_ms,
            success=True,
        )
        return MCPClientToolOutput(
            success=True,
            result=raw,
            content=content,
            latency_ms=latency_ms,
        )


def discover_mcp_tools(
    client: MCPClient,
    *,
    requires_auth: bool = True,
    category: str = "external_mcp",
) -> list[MCPClientToolAdapter]:
    """Query `tools/list` on an external MCP server and return BaseTool adapters."""
    client.initialize()
    specs = client.list_tools()
    return [
        MCPClientToolAdapter(
            client=client,
            tool_name=spec["name"],
            description=spec.get("description", ""),
            input_schema_spec=spec.get("inputSchema") or spec.get("input_schema"),
            requires_auth=requires_auth,
            category=category,
        )
        for spec in specs
    ]


def register_external_mcp_tools(
    client: MCPClient,
    *,
    registry=None,
    requires_auth: bool = True,
    category: str = "external_mcp",
) -> list[MCPClientToolAdapter]:
    """Discover remote MCP tools and register unseen tools in ToolRegistry."""
    target = registry or get_tool_registry()
    adapters = discover_mcp_tools(client, requires_auth=requires_auth, category=category)
    registered: list[MCPClientToolAdapter] = []
    for adapter in adapters:
        try:
            target.get(adapter.metadata.name)
            logger.debug("External MCP tool %s already registered; skipping", adapter.metadata.name)
        except KeyError:
            target.register(adapter)
            registered.append(adapter)
    return registered
