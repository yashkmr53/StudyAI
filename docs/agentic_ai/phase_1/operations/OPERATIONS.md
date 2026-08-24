# Phase 1 — Operations & Deployment Guide

**Date:** 2026-08-24  
**Status:** COMPLETED

---

## Environment Variables

Add to `.env` (see `.env.example` for full list):

```bash
# --- Agentic AI (Phase 1) ---
AGENT_ENABLED=true
AGENT_MAX_ITERATIONS=5
AGENT_MAX_TOOL_CALLS=10
AGENT_REQUEST_TIMEOUT_SECONDS=60
AGENT_PER_TOOL_TIMEOUT_SECONDS=30
AGENT_PROMPT_VERSION=agent_orchestrator:v1
```

## Docker Compose

No new services required. The agent runs within the existing `api` and `worker` containers.

## Database Migration

```bash
# Run once after deploying Phase 1 code
docker compose run --rm api python manage.py migrate agents
```

This creates:
- `agents_agentexecutionlog` — Audit trail for agent executions
- `agents_agentpromptversion` — Versioned agent system prompts

## Health Checks

The agent doesn't add new health check endpoints. Existing `/healthz` and `/readyz` cover the API.

## Monitoring & Alerting

### Prometheus Metrics (if PROMETHEUS_METRICS_ENABLED=true)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `agent_executions_total` | Counter | `outcome` | Total agent executions by outcome |
| `agent_tool_calls_total` | Counter | `tool`, `success` | Tool calls by tool name and success |
| `agent_iterations_histogram` | Histogram | — | Agent reasoning iterations per request |
| `agent_tool_latency_seconds` | Histogram | `tool` | Per-tool execution latency |
| `agent_token_usage_total` | Counter | `model` | Total tokens consumed |

### Key Alerts

```yaml
# Alert if agent executions fail > 5% in 5 minutes
- alert: AgentHighFailureRate
  expr: |
    rate(agent_executions_total{outcome="failed"}[5m]) 
    / rate(agent_executions_total[5m]) > 0.05
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "High agent failure rate"

# Alert if tool calls consistently fail
- alert: AgentToolFailures
  expr: |
    rate(agent_tool_calls_total{success="false"}[5m]) > 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Agent tool calls failing frequently"

# Alert if agent hits limits frequently
- alert: AgentLimitReached
  expr: |
    rate(agent_executions_total{outcome="limit_reached"}[5m]) > 5
  for: 5m
  labels:
    severity: info
  annotations:
    summary: "Agent frequently hitting iteration/tool call limits"
```

### Grafana Dashboard Panels

1. **Agent Executions Rate** — Stacked area chart by outcome (success/partial/failed/limit_reached)
2. **Tool Call Distribution** — Bar chart by tool name
3. **Tool Latency (p50/p95/p99)** — Heatmap or line chart per tool
4. **Iterations Histogram** — Distribution of reasoning steps per request
5. **Token Usage** — Line chart by model
6. **Verification Status** — Pie chart of citation verification outcomes

## Log Analysis

### Structured Log Format

```json
{
  "level": "INFO",
  "timestamp": "2026-08-24T19:30:00.123Z",
  "logger": "apps.agents.services.orchestrator",
  "request_id": "agent:abc123:xyz789",
  "message": "Agent iteration completed",
  "iteration": 2,
  "tool": "search_notes",
  "latency_ms": 245,
  "success": true,
  "evidence_count": 4
}
```

### Useful Queries

```bash
# Find slow tool executions
grep "latency_ms" /var/log/api.log | awk '$NF > 5000'

# Find failed tool calls
grep '"success": false' /var/log/api.log | jq '.tool'

# Find limit reached executions
grep '"outcome": "limit_reached"' /var/log/api.log

# Count tool usage
grep '"tool":' /var/log/api.log | sed 's/.*"tool": "\([^"]*\)".*/\1/' | sort | uniq -c | sort -rn
```

## Troubleshooting

| Issue | Diagnosis | Resolution |
|-------|-----------|------------|
| Agent returns "limit_reached" | Check iterations/tool_calls in AgentExecutionLog | Increase AGENT_MAX_ITERATIONS or AGENT_MAX_TOOL_CALLS |
| Tool calls fail with "forbidden" | Check ProfileAuthorizationService logs | Verify user owns the profile |
| Agent doesn't select expected tool | Check tool descriptions in AgentPromptVersion | Update tool descriptions in tool modules |
| Verification always "unsupported" | Check EvidenceVerifier thresholds | Adjust VERIFIER_SUPPORTED_THRESHOLD |
| High latency | Check agent_tool_latency_seconds metrics | Optimize slow tools, add caching |

## Rollback Procedure

If issues arise in production:

1. **Disable agent globally:**
   ```bash
   # Set env var and restart api
   AGENT_ENABLED=false
   docker compose restart api
   ```

2. **Disable per-user (feature flag):**
   Add user-level setting in UserProfile model (future enhancement)

3. **Rollback code:**
   ```bash
   git revert <phase-1-commit>
   docker compose up -d --build api
   docker compose run --rm api python manage.py migrate agents zero  # Remove tables
   ```

## Capacity Planning

| Resource | Baseline | With Agent (est.) |
|----------|----------|-------------------|
| API CPU | 100m | +50m per concurrent agent request |
| API Memory | 256Mi | +64Mi per concurrent agent request |
| DB Connections | 20 | +5 per concurrent agent request |
| LLM Tokens | 10k/day | +50k/day (depends on usage) |
| Redis Memory | 50Mi | +10Mi (telemetry) |

## Backup & Recovery

AgentExecutionLog tables should be included in regular PostgreSQL backups. They are append-only audit logs.

```bash
# Include in pg_dump
pg_dump -t agents_agentexecutionlog -t agents_agentpromptversion studyai > agents_backup.sql
```

## Security Considerations

1. **AgentExecutionLog** contains tool arguments/results — ensure log aggregation respects PII
2. **Prompt Injection** — LLM chain already has directive + sanitization
3. **Budget Enforcement** — `assert_within_budget()` called before agent execution
4. **Rate Limiting** — `AgentRateThrottle` (30/min) + `AIBudgetThrottle` per profile

## Performance Tuning

### Tool Timeouts (per-tool override in settings.py)

```python
AGENT_TOOL_TIMEOUTS = {
    "search_notes": 15,
    "search_reference_books": 15,
    "get_mastery": 5,
    "verify_evidence": 10,
    "get_document": 5,
    "get_subject_context": 5,
}
```

### Caching Opportunities

- `get_mastery` results cacheable for ~5 min per profile
- `get_subject_context` cacheable for ~10 min per subject
- Tool schemas cacheable indefinitely (static)

## CI/CD Integration

Add to pipeline:

```yaml
# Test agent layer
- name: Run agent tests
  run: docker compose run --rm api python -m pytest apps/agents/tests/ -v

# Check migrations
- name: Check agent migrations
  run: docker compose run --rm api python manage.py makemigrations --check --dry-run agents
```

## Known Limitations (Phase 1)

1. **No streaming** — Tool calls complete before response returned
2. **No WebSocket** — Real-time tool status requires polling
3. **Mock LLM only** — Structured output parsing optimized for mock provider
4. **Single-turn** — No conversation memory across messages (each request independent)
5. **No artifact generation** — PDF/PPTX/DOCX tools in Phase 4