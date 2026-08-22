# Environment and Secrets — after Phase 6

Delta from [`../phase_5/setup/ENVIRONMENT_AND_SECRETS.md`](../setup/ENVIRONMENT_AND_SECRETS.md):

| Variable | Required? | Purpose | Default | Used by | Rotation |
|---|---|---|---|---|---|
| `ENRICHMENT_MODEL` | No | Model name recorded per enrichment generation | `mock-gpt` | prompts registry, pipeline | Bump with model swap; recorded on new generations only |
| `VERIFIER_VERSION` | No | Evidence-verifier identity stored per citation | `sim-v1` | `EvidenceVerifier` | Bump when rules/thresholds change |
| `VERIFIER_SUPPORTED_THRESHOLD` | No | Score ≥ ⇒ supported | `0.60` | verifier | Calibrate per §26 |
| `VERIFIER_PARTIAL_THRESHOLD` | No | Score ≥ ⇒ partially_supported | `0.30` | verifier | same |

Everything else unchanged. Secret scan remains clean — no provider keys exist yet.
