# Observability — Phase 10

**Status:** Extended with Prometheus metrics endpoint and structured metrics

---

## Prometheus Metrics Endpoint

**URL:** `/metrics`  
**Enabled:** `PROMETHEUS_METRICS_ENABLED=true`  
**Content-Type:** `text/plain; version=0.0.4; charset=utf-8`

### Exposed Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ocr_fallback_total` | Counter | `provider`, `reason` | OCR fallback attempts |
| `schema_validation_failure_total` | Counter | `endpoint`, `field` | JSON schema validation failures |
| `retrieval_latency_seconds` | Histogram | `query_type` | Retrieval query latency |
| `evaluation_score` | Gauge | `metric`, `dataset` | Evaluation harness scores |
| `product_usage_total` | Counter | `feature`, `action` | User action counters |

### Example Output
```
# HELP ocr_fallback_total Total number of OCR fallback attempts
# TYPE ocr_fallback_total counter
ocr_fallback_total{provider="mock",reason="low_confidence"} 5

# HELP schema_validation_failure_total Total number of schema validation failures
# TYPE schema_validation_failure_total counter
schema_validation_failure_total{endpoint="/api/v1/documents/123/enrich",field="blocks"} 2

# HELP retrieval_latency_seconds Retrieval latency in seconds
# TYPE retrieval_latency_seconds histogram
retrieval_latency_seconds_bucket{query_type="hybrid",le="0.1"} 45
retrieval_latency_seconds_bucket{query_type="hybrid",le="0.5"} 52
retrieval_latency_seconds_count{query_type="hybrid"} 55
retrieval_latency_seconds_sum{query_type="hybrid"} 12.3

# HELP evaluation_score Evaluation score for various metrics
# TYPE evaluation_score gauge
evaluation_score{metric="citation_precision",dataset="golden_v1"} 0.87

# HELP product_usage_total Total product usage events
# TYPE product_usage_total counter
product_usage_total{feature="enrichment",action="create"} 120
```

### Internal API

```python
from shared.observability.metrics import (
    ocr_fallback_inc,
    schema_validation_failure_inc,
    retrieval_latency_observe,
    evaluation_score_set,
    product_usage_inc,
)

# In OCR chain fallback
ocr_fallback_inc(provider="tesseract", reason="low_confidence")

# In schema validation
schema_validation_failure_inc(endpoint="/api/v1/documents/123/enrich", field="blocks")

# In retrieval service
retrieval_latency_observe(query_type="hybrid", latency_seconds=0.234)

# In evaluation harness
evaluation_score_set(metric="citation_precision", dataset="golden_v1", value=0.87)

# In feature code
product_usage_inc(feature="enrichment", action="create")
```

### Scraping Configuration (Prometheus)

```yaml
scrape_configs:
  - job_name: 'studyai-backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

---

## Structured Logging (Existing)

Format: `{levelname} {asctime} {name} request_id={request_id} {message}`

### Key Log Points (Phase 10)
- `daily_backup` task start/completion
- Offsite hook invocation result
- Budget exceeded events
- Coalescing decisions
- Prompt redaction counts

---

## Health/Readiness/Status Endpoints (Existing)

| Endpoint | Purpose | Auth |
|----------|---------|------|
| `/healthz` | Liveness (process up) | None |
| `/readyz` | Readiness (DB roundtrip) | None |
| `/api/v1/status` | Internal aggregates (jobs, providers, citations, latency) | Staff only |

---

## Alerting Recommendations (Phase 11)

| Alert | Condition | Severity |
|-------|-----------|----------|
| BackupFailed | `backup.completed` not in AuditLog for 26h | Critical |
| ThrottleHigh | `rate_limited` > 100/min | Warning |
| BudgetExceeded | Many 429 with budget details | Info |
| DeadLetterGrowing | `failed_dead_letter` > 10 | Warning |
| RetrievalLatencyP99 | p99 > 2s | Warning |

---

## Related Documentation

- `docs/phase_10/architecture/SYSTEM_FLOWS.md` — Metrics collection flow
- `docs/phase_10/architecture/ARCHITECTURE.md` — Component diagram
- `docs/phase_6/operations/OBSERVABILITY.md` — Base observability spec