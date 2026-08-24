"""MCP Token Validator (Phase 3).

Validates MCP requests and enforces authorization.
"""
import secrets
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.profiles.models import Profile

logger = logging.getLogger(__name__)

User = get_user_model()


class MCPAuthError(ValueError):
    """MCP authentication error with error code."""
    def __init__(self, message: str, code: int = -32000):
        super().__init__(message)
        self.code = code


@dataclass
class MCPUserContext:
    """Context for an authenticated MCP request."""
    user_id: int
    user: User
    profile: Profile
    request_id: str
    client_id: str
    scopes: list[str] = field(default_factory=list)
    expires_at: Optional[float] = None


@dataclass
class MCPToken:
    """MCP access token."""
    token: str
    user_id: int
    client_id: str
    scopes: list[str]
    created_at: float
    expires_at: float
    revoked: bool = False


class MCPAuthenticator:
    """Handles MCP client authentication."""
    
    # Token prefix for identification
    TOKEN_PREFIX = "mcp_"
    DEFAULT_TTL_HOURS = 24
    MAX_TTL_HOURS = 168  # 1 week
    
    def __init__(self):
        self.token_cache_prefix = "mcp_token:"
        self.client_cache_prefix = "mcp_client:"
    
    def create_token(
        self,
        user: User,
        client_id: str,
        scopes: list[str] | None = None,
        ttl_hours: int | None = None,
    ) -> MCPToken:
        """Create a new MCP access token for a user."""
        ttl_hours = ttl_hours or self.DEFAULT_TTL_HOURS
        ttl_hours = min(ttl_hours, self.MAX_TTL_HOURS)
        
        token_str = f"{self.TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
        now = time.time()
        
        token = MCPToken(
            token=token_str,
            user_id=user.pk,
            client_id=client_id,
            scopes=scopes or ["tools:read", "tools:execute"],
            created_at=now,
            expires_at=now + (ttl_hours * 3600),
        )
        
        # Store in cache
        cache_key = f"{self.token_cache_prefix}{token_str}"
        cache.set(cache_key, token, timeout=int(ttl_hours * 3600))
        
        # Track client
        client_key = f"{self.client_cache_prefix}{client_id}"
        client_data = cache.get(client_key, {"tokens": [], "created_at": now})
        client_data["tokens"].append(token_str)
        cache.set(client_key, client_data, timeout=int(self.MAX_TTL_HOURS * 3600))
        
        logger.info("MCP token created: client=%s user=%s scopes=%s", client_id, user.pk, token.scopes)
        return token
    
    def validate_token(self, token_str: str) -> Optional[MCPToken]:
        """Validate an MCP token and return token data if valid."""
        if not token_str or not token_str.startswith(self.TOKEN_PREFIX):
            return None
        
        cache_key = f"{self.token_cache_prefix}{token_str}"
        token = cache.get(cache_key)
        
        if not token:
            return None
        
        if token.revoked:
            logger.warning("MCP token revoked: %s", token_str[:20])
            return None
        
        if time.time() > token.expires_at:
            logger.warning("MCP token expired: %s", token_str[:20])
            self.revoke_token(token_str)
            return None
        
        return token
    
    def revoke_token(self, token_str: str) -> bool:
        """Revoke an MCP token."""
        cache_key = f"{self.token_cache_prefix}{token_str}"
        token = cache.get(cache_key)
        
        if token:
            token.revoked = True
            cache.set(cache_key, token, timeout=3600)  # Keep for 1 hour for audit
            logger.info("MCP token revoked: %s", token_str[:20])
            return True
        
        return False
    
    def revoke_all_user_tokens(self, user_id: int) -> int:
        """Revoke all tokens for a user."""
        # This is expensive - would need to scan all tokens
        # For now, we'll just note it and handle at validation time
        cache.set(f"mcp_user_revoked:{user_id}", time.time(), timeout=86400 * 30)
        return 0
    
    def get_user_context(self, token: MCPToken, request_id: str) -> MCPUserContext:
        """Get user context from validated token."""
        try:
            user = User.objects.get(pk=token.user_id)
            profile = Profile.objects.get(user=user)
        except (User.DoesNotExist, Profile.DoesNotExist):
            raise ValueError("User or profile not found")
        
        # Check if user was globally revoked
        revoked_at = cache.get(f"mcp_user_revoked:{token.user_id}")
        if revoked_at and revoked_at > token.created_at:
            raise ValueError("User tokens revoked")
        
        return MCPUserContext(
            user_id=user.pk,
            user=user,
            profile=profile,
            request_id=request_id,
            client_id=token.client_id,
            scopes=token.scopes,
            expires_at=token.expires_at,
        )


class MCPTokenValidator:
    """Validates MCP requests and enforces authorization."""
    
    # Required scopes for different tool categories
    CATEGORY_SCOPES = {
        "retrieval": ["tools:read", "tools:execute"],
        "learning": ["tools:read", "tools:execute", "learning:read"],
        "evidence": ["tools:read", "tools:execute"],
        "document": ["tools:read", "tools:execute", "documents:read"],
    }
    
    def __init__(self, authenticator: MCPAuthenticator):
        self.authenticator = authenticator
    
    def validate_request(
        self,
        auth_header: str | None,
        tool_name: str,
        tool_category: str,
    ) -> MCPUserContext:
        """Validate an MCP request and return user context."""
        if not auth_header:
            raise MCPAuthError("Missing Authorization header", code=-32000)
        
        # Support both "Bearer <token>" and raw token
        token_str = auth_header
        if auth_header.startswith("Bearer "):
            token_str = auth_header[7:]
        
        token = self.authenticator.validate_token(token_str)
        if not token:
            raise MCPAuthError("Invalid or expired token", code=-32000)
        
        # Check scopes
        required_scopes = self.CATEGORY_SCOPES.get(tool_category, ["tools:execute"])
        if not any(scope in token.scopes for scope in required_scopes):
            raise MCPAuthError(
                f"Insufficient scopes for {tool_category}. Required: {required_scopes}",
                code=-32001
            )
        
        # Get user context
        request_id = f"mcp:{secrets.token_urlsafe(8)}"
        return self.authenticator.get_user_context(token, request_id)
    
    def check_tool_access(self, user_context: MCPUserContext, tool_name: str, tool_category: str) -> bool:
        """Check if user context has access to a specific tool."""
        # Base scope check
        required_scopes = self.CATEGORY_SCOPES.get(tool_category, ["tools:execute"])
        if not any(scope in user_context.scopes for scope in required_scopes):
            return False
        
        # Additional profile-based checks could go here
        # e.g., check if user has access to the subject/document
        
        return True


# Rate limiting for MCP
class MCPRateLimiter:
    """Rate limiter for MCP requests."""
    
    def __init__(self):
        self.default_limit = getattr(settings, "MCP_RATE_LIMIT", 60)  # requests per minute
        self.burst_limit = getattr(settings, "MCP_BURST_LIMIT", 10)
    
    def check_rate_limit(self, client_id: str, limit: int | None = None) -> tuple[bool, dict]:
        """Check if client is within rate limits. Returns (allowed, headers)."""
        limit = limit or self.default_limit
        cache_key = f"mcp_ratelimit:{client_id}"
        
        current = cache.get(cache_key, 0)
        
        if current >= limit:
            # Rate limited
            ttl = cache.ttl(cache_key)
            return False, {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time() + (ttl or 60))),
                "Retry-After": str(ttl or 60),
            }
        
        # Increment counter
        cache.set(cache_key, current + 1, timeout=60)
        
        return True, {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(limit - current - 1),
            "X-RateLimit-Reset": str(int(time.time() + 60)),
        }