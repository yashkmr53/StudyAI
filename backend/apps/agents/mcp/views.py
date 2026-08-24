"""MCP HTTP Views (Phase 3).

Django views for MCP over HTTP/SSE.
"""
import json
import logging

from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings

from apps.agents.mcp.server import create_mcp_server, MCPServer
from apps.agents.mcp.auth import MCPAuthenticator, MCPTokenValidator, MCPRateLimiter
from apps.agents.mcp.registry import get_mcp_tool_registry

logger = logging.getLogger(__name__)


# Global server instance (initialized lazily)
_mcp_server: "MCPServer | None" = None


def get_mcp_server() -> "MCPServer":
    """Get or create the global MCP server instance."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = create_mcp_server(
            rate_limiter=MCPRateLimiter(),
        )
    return _mcp_server


@method_decorator(csrf_exempt, name="dispatch")
class MCPHTTPView(View):
    """HTTP endpoint for MCP JSON-RPC requests."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.server = get_mcp_server()
    
    def post(self, request):
        """Handle JSON-RPC request over HTTP."""
        try:
            if request.content_type != "application/json":
                return JsonResponse(
                    {"error": "Content-Type must be application/json"},
                    status=400,
                )
            
            request_data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}},
                status=400,
            )
        
        auth_header = request.headers.get("Authorization")
        
        # Handle request
        response = self.server.handle_request(request_data, auth_header)
        
        # Create response
        resp = JsonResponse(response.to_dict())
        
        # Add CORS headers for MCP clients
        resp["Access-Control-Allow-Origin"] = "*"
        resp["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        
        return resp
    
    def options(self, request):
        """Handle CORS preflight."""
        resp = JsonResponse({})
        resp["Access-Control-Allow-Origin"] = "*"
        resp["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp["Access-Control-Max-Age"] = "86400"
        return resp


class MCPTokenView(View):
    """Endpoint for creating/revoking MCP tokens."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from apps.agents.mcp.auth import MCPAuthenticator
        self.authenticator = MCPAuthenticator()
    
    def post(self, request):
        """Create a new MCP token."""
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        
        # Require authentication (use existing session auth)
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        
        client_id = data.get("client_id", f"client_{request.user.pk}_{int(time.time())}")
        scopes = data.get("scopes", ["tools:read", "tools:execute"])
        ttl_hours = data.get("ttl_hours", 24)
        
        # Validate scopes
        valid_scopes = [
            "tools:read", "tools:execute", "learning:read", "documents:read"
        ]
        scopes = [s for s in scopes if s in valid_scopes]
        if not scopes:
            scopes = ["tools:read", "tools:execute"]
        
        # Create token
        from apps.agents.mcp.auth import MCPAuthenticator
        authenticator = MCPAuthenticator()
        token = authenticator.create_token(
            user=request.user,
            client_id=client_id,
            scopes=scopes,
            ttl_hours=ttl_hours,
        )
        
        return JsonResponse({
            "token": token.token,
            "expires_at": token.expires_at,
            "scopes": token.scopes,
            "client_id": token.client_id,
        })
    
    def delete(self, request):
        """Revoke an MCP token."""
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        
        token_str = data.get("token")
        if not token_str:
            return JsonResponse({"error": "Token required"}, status=400)
        
        from apps.agents.mcp.auth import MCPAuthenticator
        authenticator = MCPAuthenticator()
        success = authenticator.revoke_token(token_str)
        
        return JsonResponse({"revoked": success})
    
    def get(self, request):
        """List user's MCP tokens (metadata only)."""
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        
        # This would require scanning all tokens - simplified for now
        return JsonResponse({
            "tokens": [],
            "message": "Token listing requires additional storage. Use the token directly.",
        })


# Import time for MCPTokenView
import time