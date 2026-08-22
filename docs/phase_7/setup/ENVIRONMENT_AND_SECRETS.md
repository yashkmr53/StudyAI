# Environment and Secrets — after Phase 7

Delta from [`../phase_6/setup/ENVIRONMENT_AND_SECRETS.md`](../setup/ENVIRONMENT_AND_SECRETS.md):

| Variable | Required? | Purpose | Default | Used by | Rotation |
|---|---|---|---|---|---|
| `QUESTION_PROMPT_VERSION` | No | Question-generation prompt identity recorded per question | `v1` | QuestionGenerationService | Bump with prompt changes |
| `PLANNER_W_WEAKNESS` / `_URGENCY` / `_FAILURES` / `_INSUFFICIENT` | No | Planner priority weights | 0.45 / 0.25 / 0.20 / 0.10 | RevisionPlanningService.build_plan | Tune via evaluation |

Mastery EMA constants are module-level in `apps/tests/services.py` (G-005) pending calibration. Everything else unchanged; secret scan clean.
