"""MCP Observability & Telemetry (Phase 3).

Extends existing telemetry for MCP-specific metrics.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from django.conf import settings
from django.db import transaction

from shared.observability.metrics import incr

logger = logging.getLogger(__name__)


@dataclass
class MCPCallRecord:
    """Record of an MCP tool call."""
    tool_name: str
    client_id: str
    user_id: int
    request_id: str
    latency_ms: int
    success: bool
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0


# In-memory ring buffer for recent MCP calls
_mcp_calls: list[MCPCallRecord] = []
_mcp_calls_max = 1000


def record_mcp_call(
    *,
    tool_name: str,
    client_id: str,
    user_id: int,
    request_id: str,
    latency_ms: int,
    success: bool,
    error: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Record an MCP tool call for telemetry."""
    record = MCPCallRecord(
        tool_name=tool_name,
        client_id=client_id,
        user_id=user_id,
        request_id=request_id,
        latency_ms=latency_ms,
        success=success,
        error=error,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    
    # Add to ring buffer
    _mcp_calls.append(record)
    if len(_mcp_calls) > _mcp_calls_max:
        _mcp_calls.pop(0)
    
    # Emit Prometheus metrics
    incr("mcp_calls_total", 1)
    incr(f"mcp_calls_total.{tool_name}", 1)
    incr(f"mcp_calls_total.{'success' if success else 'error'}", 1)
    incr(f"mcp_calls_total.client.{client_id}", 1)
    
    # Log structured
    logger.info(
        "MCP call: tool=%s client=%s user=%s latency_ms=%d success=%s request_id=%s",
        tool_name, client_id, user_id, latency_ms, success, request_id
    )


def get_mcp_stats() -> dict:
    """Get MCP call statistics."""
    if not _mcp_calls:
        return {
            "total_calls": 0,
            "success_rate": 0.0,
            "avg_latency_ms": 0,
            "by_tool": {},
            "by_client": {},
        }
    
    total = len(_mcp_calls)
    successful = sum(1 for c in _mcp_calls if c.success)
    total_latency = sum(c.latency_ms for c in _mcp_calls)
    
    by_tool = {}
    by_client = {}
    
    for call in _mcp_calls:
        by_tool[call.tool_name] = by_tool.get(call.tool_name, 0) + 1
        by_client[call.client_id] = by_client.get(call.client_id, 0) + 1
    
    return {
        "total_calls": total,
        "success_rate": round(successful / total, 4) if total > 0 else 0,
        "avg_latency_ms": round(total_latency / total, 2) if total > 0 else 0,
        "by_tool": by_tool,
        "by_client": by_client,
    }


def get_recent_mcp_calls(limit: int = 100) -> list[dict]:
    """Get recent MCP calls for debugging."""
    return [
        {
            "tool": c.tool_name,
            "client": c.client_id,
            "user": c.user_id,
            "request_id": c.request_id,
            "latency_ms": c.latency_ms,
            "success": c.success,
            "error": c.error,
            "timestamp": time.time() if False else None,  # Would need to store timestamp
        }
        for c in _mcp_calls[-limit:]
    ]


# Import time for the above
import time