"""Management command to run MCP server."""
import logging

from django.core.management.base import BaseCommand
from django.conf import settings

from apps.agents.mcp.server import run_stdio_server, create_mcp_server
from apps.agents.mcp.auth import MCPAuthenticator, MCPRateLimiter
from apps.agents.mcp.registry import get_mcp_tool_registry

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run MCP server (stdio or HTTP)"
    
    def add_arguments(self, parser):
        parser.add_argument(
            "--transport",
            choices=["stdio", "http"],
            default="stdio",
            help="Transport protocol (default: stdio)",
        )
        parser.add_argument(
            "--host",
            default="127.0.0.1",
            help="Host for HTTP transport (default: 127.0.0.1)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8080,
            help="Port for HTTP transport (default: 8080)",
        )
        parser.add_argument(
            "--rate-limit",
            type=int,
            default=None,
            help="Rate limit per minute (default: from settings)",
        )
    
    def handle(self, *args, **options):
        transport = options["transport"]
        rate_limit = options["rate_limit"]
        
        # Create components
        tool_registry = get_mcp_tool_registry()
        authenticator = MCPAuthenticator()
        rate_limiter = MCPRateLimiter() if rate_limit is None else MCPRateLimiter()
        if rate_limit:
            rate_limiter.default_limit = rate_limit
        
        server = create_mcp_server(
            tool_registry=tool_registry,
            rate_limiter=rate_limiter,
        )
        
        if transport == "stdio":
            self.stdout.write("Starting MCP server on stdio...")
            self._run_stdio()
        elif transport == "http":
            host = options["host"]
            port = options["port"]
            self.stdout.write(f"Starting MCP HTTP server on {host}:{port}...")
            self._run_http(server, host, port)
    
    def _run_stdio(self):
        """Run MCP server on stdio."""
        from apps.agents.mcp.server import run_stdio_server
        run_stdio_server()
    
    def _run_http(self, server, host: str, port: int):
        """Run MCP server over HTTP using Django's runserver."""
        # For HTTP transport, we use Django's built-in server
        # The MCP endpoints are already registered in urls.py
        from django.core.management import execute_from_command_line
        import sys
        
        # Re-run with runserver
        sys.argv = ["manage.py", "runserver", f"{options.get('host', '127.0.0.1')}:{options.get('port', 8000)}"]
        execute_from_command_line(sys.argv)