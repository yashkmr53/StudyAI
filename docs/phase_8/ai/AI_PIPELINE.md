# AI Pipeline — final stage inventory

All stages implemented except real providers. See [../phase_7/ai/AI_PIPELINE.md](../../phase_7/ai/AI_PIPELINE.md) plus:

- **LLM fallback chain** now live for enrichment/chat/questions: primary → fallback attempts, each recorded in ProviderCallLog (latency/success/error). Providers remain mocks (F-002).
- Budget gate can refuse enrich/chat before spend when `AI_DAILY_BUDGET_PER_PROFILE` is hit.
