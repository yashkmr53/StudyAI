"""MCP Server (Phase 3).

Implements the Model Context Protocol (MCP) server for StudyAI.
Supports JSON-RPC 2.0 over HTTP/SSE and stdio.
"""
import json
import logging
import secrets
import time
from dataclasses import dataclass, asdict
from typing import Any, Optional, Callable
from enum import Enum

from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse, HttpRequest
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.agents.mcp.registry import get_mcp_tool_registry, MCPToolRegistry
from apps.agents.mcp.auth import (
    MCPAuthenticator,
    MCPTokenValidator,
    MCPRateLimiter,
    MCPUserContext,
)

logger = logging.getLogger(__name__)


class MCPErrorCode(Enum):
    """MCP/JSON-RPC error codes."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    AUTHENTICATION_FAILED = -32000
    AUTHORIZATION_FAILED = -32001
    RATE_LIMITED = -32002
    TOOL_NOT_FOUND = -32003
    TOOL_EXECUTION_FAILED = -32004


@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 request."""
    jsonrpc: str = "2.0"
    id: Optional[Any] = None
    method: str = ""
    params: dict = None
    
    def __post_init__(self):
        if self.params is None:
            self.params = {}


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 response."""
    jsonrpc: str = "2.0"
    id: Optional[Any] = None
    result: Any = None
    error: dict = None
    
    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


class MCPServer:
    """MCP Server implementation."""
    
    def __init__(
        self,
        tool_registry: MCPToolRegistry | None = None,
        authenticator: MCPAuthenticator | None = None,
        token_validator: MCPTokenValidator | None = None,
        rate_limiter: Optional["MCPRateLimiter"] = None,
    ):
        self.tool_registry = tool_registry or get_mcp_tool_registry()
        self.authenticator = authenticator or MCPAuthenticator()
        self.token_validator = token_validator or MCPTokenValidator(self.authenticator)
        self.rate_limiter = rate_limiter
        
        # Method handlers
        self.methods = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "ping": self._handle_ping,
        }
    
    def handle_request(self, request_data: dict, auth_header: str | None = None) -> JSONRPCResponse:
        """Handle a JSON-RPC request."""
        try:
            req = JSONRPCRequest(**request_data)
        except (TypeError, ValueError) as e:
            return self._error_response(
                request_data.get("id"),
                MCPErrorCode.INVALID_REQUEST,
                f"Invalid request format: {e}",
            )
        
        # Validate JSON-RPC version
        if req.jsonrpc != "2.0":
            return self._error_response(req.id, MCPErrorCode.INVALID_REQUEST, "Unsupported JSON-RPC version")
        
        # Get handler
        handler = self.methods.get(req.method)
        if not handler:
            return self._error_response(req.id, MCPErrorCode.METHOD_NOT_FOUND, f"Method not found: {req.method}")
        
        try:
            result = handler(req.params, auth_header)
            return JSONRPCResponse(id=req.id, result=result)
        except ValueError as e:
            return self._error_response(req.id, MCPErrorCode.INVALID_PARAMS, str(e))
        except PermissionError as e:
            return self._error_response(req.id, MCPErrorCode.AUTHORIZATION_FAILED, str(e))
        except Exception as e:
            logger.exception("MCP method error: %s", req.method)
            return self._error_response(req.id, MCPErrorCode.INTERNAL_ERROR, f"Internal error: {e}")
    
    def _handle_initialize(self, params: dict, auth_header: str | None) -> dict:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": True},
            },
            "serverInfo": {
                "name": "StudyAI",
                "version": "1.0.0",
            },
        }
    
    def _handle_ping(self, params: dict, auth_header: str | None) -> dict:
        """Handle ping request."""
        return {"status": "ok", "timestamp": time.time()}
    
    def _handle_tools_list(self, params: dict, auth_header: str | None) -> dict:
        """Handle tools/list request."""
        # No auth required for listing tools
        tools = self.tool_registry.get_tool_definitions()
        return {"tools": tools}
    
    def _handle_tools_call(self, params: dict, auth_header: str | None) -> dict:
        """Handle tools/call request."""
        # Extract parameters
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            raise ValueError("Missing tool name")
        
        # Get tool info for category
        mcp_tool = self.tool_registry.get_tool(tool_name)
        if not mcp_tool:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        tool_category = mcp_tool.category
        
        # Validate authentication and authorization
        user_context = self.token_validator.validate_request(auth_header, tool_name, tool_category)
        
        # Check rate limit
        if self.rate_limiter:
            allowed, rate_headers = self.rate_limiter.check_rate_limit(user_context.client_id)
            if not allowed:
                raise PermissionError("Rate limit exceeded")
        
        # Check tool-specific access
        if not self.token_validator.check_tool_access(user_context, tool_name, tool_category):
            raise PermissionError(f"Access denied to tool: {tool_name}")
        
        # Execute tool
        logger.info(
            "MCP tool call: tool=%s client=%s user=%s request_id=%s",
            tool_name, user_context.client_id, user_context.user_id, user_context.request_id
        )
        
        start_time = time.time()
        success = False
        error = None
        try:
            result = self.tool_registry.call_tool(tool_name, arguments, user_context)
            latency_ms = int((time.time() - start_time) * 1000)
            success = True
            
            # Add MCP metadata to result
            if isinstance(result, dict):
                result["_mcp"] = {
                    "latency_ms": latency_ms,
                    "request_id": user_context.request_id,
                }
            
            # Record telemetry
            from apps.agents.mcp.telemetry import record_mcp_call
            record_mcp_call(
                tool_name=tool_name,
                client_id=user_context.client_id,
                user_id=user_context.user_id,
                request_id=user_context.request_id,
                latency_ms=latency_ms,
                success=True,
            )
            
            return result
            
        except ValueError as e:
            error = str(e)
            raise ValueError(f"Tool execution failed: {e}")
        except Exception as e:
            error = str(e)
            logger.exception("MCP tool execution error: %s", tool_name)
            raise ValueError(f"Tool execution failed: {e}")
        finally:
            latency_ms = int((time.time() - start_time) * 1000)
            # Record telemetry for failures too
            from apps.agents.mcp.telemetry import record_mcp_call
            record_mcp_call(
                tool_name=tool_name,
                client_id=user_context.client_id,
                user_id=user_context.user_id,
                request_id=user_context.request_id,
                latency_ms=latency_ms,
                success=success,
                error=error,
            )
    
    def _error_response(self, id: Any, code: MCPErrorCode, message: str, data: Any = None) -> JSONRPCResponse:
        """Create an error response."""
        error = {"code": code.value, "message": message}
        if data is not None:
            error["data"] = data
        return JSONRPCResponse(id=id, error=error)


@method_decorator(csrf_exempt, name="dispatch")
class MCPHTTPView(View):
    """Django view for MCP over HTTP/SSE."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.server = create_mcp_server()
    
    def post(self, request: HttpRequest) -> JsonResponse:
        """Handle JSON-RPC request over HTTP."""
        try:
            # Parse JSON body
            if request.content_type == "application/json":
                request_data = json.loads(request.body)
            else:
                return JsonResponse(
                    self.server._error_response(None, MCPErrorCode.INVALID_REQUEST, "Content-Type must be application/json").to_dict(),
                    status=400,
                )
        except json.JSONDecodeError as e:
            return JsonResponse(
                self.server._error_response(None, MCPErrorCode.PARSE_ERROR, f"Invalid JSON: {e}").to_dict(),
                status=400,
            )
        
        auth_header = request.headers.get("Authorization")
        response = self.server.handle_request(request_data, auth_header)
        
        # Add rate limit headers if present
        resp = JsonResponse(response.to_dict())
        return resp


def create_mcp_server(
    tool_registry: MCPToolRegistry | None = None,
    authenticator: MCPAuthenticator | None = None,
    token_validator: MCPTokenValidator | None = None,
    rate_limiter: Optional["MCPRateLimiter"] = None,
) -> MCPServer:
    """Create and configure an MCP server instance."""
    return MCPServer(
        tool_registry=tool_registry,
        authenticator=authenticator,
        token_validator=token_validator,
        rate_limiter=rate_limiter,
    )


# Standalone MCP server for stdio transport
class MCPStdioServer:
    """MCP server for stdio transport (for CLI clients)."""
    
    def __init__(self, server: MCPServer):
        self.server = server
        self.running = False
    
    def run(self) -> None:
        """Run the stdio server loop."""
        self.running = True
        logger.info("MCP stdio server started")
        
        while self.running:
            try:
                line = input()
                if not line:
                    continue
                
                request_data = json.loads(line)
                auth_header = None  # No auth for stdio (local only)
                
                response = self.server.handle_request(request_data, auth_header)
                print(json.dumps(response.to_dict()), flush=True)
                
            except EOFError:
                break
            except json.JSONDecodeError as e:
                error_resp = self.server._error_response(None, MCPErrorCode.PARSE_ERROR, f"Invalid JSON: {e}")
                print(json.dumps(error_resp.to_dict()), flush=True)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.exception("Stdio server error")
                error_resp = self.server._error_response(None, MCPErrorCode.INTERNAL_ERROR, str(e))
                print(json.dumps(error_resp.to_dict()), flush=True)
        
        logger.info("MCP stdio server stopped")


# Management command to run stdio server
def run_stdio_server() -> None:
    """Run MCP server over stdio."""
    server = create_mcp_server()
    stdio_server = MCPStdioServer(server)
    stdio_server.run()