"""Agent API URLs (Phase 1 & 3)."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.agents.views import AgentViewSet
from apps.agents.mcp.views import MCPHTTPView, MCPTokenView

router = DefaultRouter()
router.register(r"", AgentViewSet, basename="agent")

urlpatterns = [
    path("", include(router.urls)),
    # MCP endpoints (Phase 3)
    path("mcp/", MCPHTTPView.as_view(), name="mcp-endpoint"),
    path("mcp/token/", MCPTokenView.as_view(), name="mcp-token"),
]