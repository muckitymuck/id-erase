# Tool Conventions

## erasure_plan tool
The only execution tool available. All broker interactions flow through this tool.

### Actions
- `start` — begin a broker plan run
- `status` — check run progress
- `approve` — resolve an approval gate
- `artifact_get` — retrieve run artifacts

### Rules
- Always include `idempotency_key` to prevent duplicate submissions
- Never call `approve` without presenting the approval prompt to the operator first
- Poll `status` at reasonable intervals (5-10 seconds)
- Report artifact contents without exposing raw PII
