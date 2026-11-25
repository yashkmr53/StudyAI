"""MCP HTTP Views (Phase 3).

Django views for MCP over HTTP/SSE.
"""
import json
import logging
import time

from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

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


class MCPTokenView(APIView):
    """Endpoint for creating/revoking MCP tokens."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.authenticator = MCPAuthenticator()

    def post(self, request):
        """Create a new MCP token."""
        data = request.data if isinstance(request.data, dict) else {}

        client_id = data.get("client_id", f"client_{request.user.pk}_{int(time.time())}")
        scopes = data.get("scopes", ["tools:read", "tools:execute"])
        ttl_hours = data.get("ttl_hours", 24)
        profile_id = request.headers.get("X-Active-Profile") or data.get("profile_id")

        # Validate scopes
        valid_scopes = [
            "tools:read", "tools:execute", "learning:read", "documents:read"
        ]
        scopes = [s for s in scopes if s in valid_scopes]
        if not scopes:
            scopes = ["tools:read", "tools:execute"]

        token = self.authenticator.create_token(
            user=request.user,
            client_id=client_id,
            scopes=scopes,
            ttl_hours=ttl_hours,
            profile_id=profile_id,
        )

        return Response({
            "token": token.token,
            "expires_at": token.expires_at,
            "scopes": token.scopes,
            "client_id": token.client_id,
        })

    def delete(self, request):
        """Revoke an MCP token."""
        data = request.data if isinstance(request.data, dict) else {}
        token_str = data.get("token")
        if not token_str:
            return Response({"error": "Token required"}, status=status.HTTP_400_BAD_REQUEST)

        token_obj = self.authenticator.validate_token(token_str)
        if token_obj and token_obj.user_id != request.user.pk:
            return Response({"revoked": False}, status=status.HTTP_403_FORBIDDEN)

        success = self.authenticator.revoke_token(token_str)
        return Response({"revoked": success})

    def get(self, request):
        """List user's MCP tokens (metadata only)."""
        return Response({
            "tokens": [],
            "message": "Token listing requires additional storage. Use the token directly.",
        })