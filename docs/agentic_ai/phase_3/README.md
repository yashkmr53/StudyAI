# Phase 3 — MCP Integration

**Date:** 2026-08-24  
**Status:** COMPLETED

---

## Overview

Phase 3 implements the Model Context Protocol (MCP) adapter that exposes StudyAI's 12 tools via the standard MCP interface. This enables any MCP-compatible client (Claude Desktop, VS Code extensions, custom agents) to use StudyAI's capabilities.

---

## Architecture

```
MCP Client (Claude Desktop, etc.)
         │
         ▼
┌─────────────────────────────────────┐
│        MCP HTTP Endpoint            │
│   POST /api/v1/agents/mcp/          │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│         MCP Server                  │
│  JSON-RPC 2.0 Handler               │
│  - initialize                       │
│  - tools/list                       │
│  - tools/call                       │
│  - ping                             │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      MCP Tool Registry              │
│  Maps 12 StudyAI tools to MCP       │
│  with JSON Schema definitions       │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      StudyAI Internal Tools         │
│  (via existing tool layer)          │
└─────────────────────────────────────┘
```

---

## Quick Start

### 1. Get MCP Token

```bash
# Via API (requires session auth)
curl -X POST http://localhost:8000/api/v1/agents/mcp/token/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <session_token>" \
  -d '{"client_id": "my-client", "scopes": ["tools:read", "tools:execute"]}'

# Response:
# {"token": "mcp_abc123...", "expires_at": 1234567890, "scopes": ["tools:read", "tools:execute"]}
```

### 2. Use with MCP Client

Configure your MCP client (e.g., Claude Desktop) to connect to:

```
URL: http://localhost:8000/api/v1/agents/mcp/
Auth: Bearer mcp_abc123...
```

Or use the stdio transport:

```bash
docker compose run --rm api python manage.py mcp_server --transport stdio
```

---

## Available Tools (12)

| Tool | Category | Description |
|------|----------|-------------|
| `search_notes` | retrieval | Hybrid search over user notes |
| `search_reference_books` | retrieval | Search READY reference books |
| `get_mastery` | learning | Mastery overview per tag |
| `get_revision_plan` | learning | Deterministic revision plan |
| `get_previous_questions` | learning | Previously generated questions |
| `generate_questions` | learning | Generate MCQs from document |
| `create_test` | learning | Create adaptive test |
| `verify_evidence` | evidence | Verify content against sources |
| `verify_citations` | evidence | Batch verify citations |
| `get_document` | document | Document metadata |
| `get_subject_context` | document | Subject context with docs/tags |
| `mastery_aware_test_generation` | learning | Full weak-topic test workflow |

---

## Example Usage

### List Tools

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}
```

### Call Tool

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "search_notes",
    "arguments": {
      "query": "neural networks backpropagation",
      "top_k": 5
    }
  }
}
```

### Response

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "results": [
      {
        "chunk_id": "uuid",
        "document_id": "uuid",
        "source_type": "note",
        "page_start": 1,
        "page_end": 2,
        "snippet": "Backpropagation computes gradients...",
        "scores": {"dense": 0.85, "keyword": 0.72, "rrf": 0.78}
      }
    ],
    "query": "neural networks backpropagation",
    "_mcp": {
      "latency_ms": 145,
      "request_id": "mcp:abc123"
    }
  }
}
```

---

## Token Management

### Create Token

```bash
curl -X POST http://localhost:8000/api/v1/agents/mcp/token/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <session_token>" \
  -d '{
    "client_id": "my-app",
    "scopes": ["tools:read", "tools:execute", "learning:read"],
    "ttl_hours": 48
  }'
```

### Revoke Token

```bash
curl -X DELETE http://localhost:8000/api/v1/agents/mcp/token/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <session_token>" \
  -d '{"token": "mcp_abc123..."}'
```

---

## Scopes Reference

| Scope | Grants Access To |
|-------|------------------|
| `tools:read` | List tools, view schemas |
| `tools:execute` | Execute any tool |
| `learning:read` | Learning tools (mastery, revision, questions) |
| `documents:read` | Document tools |

### Category Requirements

| Category | Required Scopes |
|----------|-----------------|
| retrieval | `tools:read` OR `tools:execute` |
| learning | `tools:read` OR `tools:execute` OR `learning:read` |
| evidence | `tools:read` OR `tools:execute` |
| document | `tools:read` OR `tools:execute` OR `documents:read` |

---

## Configuration

```python
# settings.py
MCP_RATE_LIMIT = 60          # requests per minute per client
MCP_BURST_LIMIT = 10         # burst allowance
```

---

## Running the MCP Server

### Stdio Transport (for local CLI clients)

```bash
docker compose run --rm api python manage.py mcp_server --transport stdio
```

### HTTP Transport (already running)

The HTTP endpoint is automatically available at `/api/v1/agents/mcp/` when the API server runs.

---

## Testing

```bash
# Run MCP tests
docker compose run --rm api python -m pytest apps/agents/tests/test_mcp.py -v

# All agent tests
docker compose run --rm api python -m pytest apps/agents/tests/ -v
```

---

## Security Notes

1. **Token Storage**: Tokens stored in Redis cache with TTL
2. **Revocation**: Tokens can be revoked individually or all for a user
3. **Profile Isolation**: Tools enforce profile ownership at execution
4. **Rate Limiting**: Per-client rate limiting prevents abuse
5. **Audit Trail**: All tool calls logged with request_id, client_id, user_id

---

## Future Enhancements (Phase 4+)

- SSE transport for streaming responses
- Tool annotations for better client UX
- Resource support (files, documents)
- Circuit breakers for tool failures
- Advanced rate limiting (token bucket)
- MCP resource support