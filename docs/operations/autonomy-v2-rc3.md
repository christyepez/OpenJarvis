# OpenJarvis Autonomy V2 — 2.0.0-rc3

## Delta from rc2

- Adds bidirectional n8n result delivery.
- Adds `POST /webhook/jarvis/result` to the bundled n8n workflow.
- Terminal `completed`, `failed`, and `cancelled` tasks can notify n8n.
- Supports an explicit per-task `resultCallbackUrl`.
- Supports `OPENJARVIS_N8N_RESULT_WEBHOOK_URL` as the default result endpoint.
- Result callback failures are recorded in task context without changing the terminal task result.
- Includes task cancel/resume operator controls from the previous checkpoint.

## End-to-end contract

```text
goal
-> planner
-> approval policy
-> TaskStore
-> n8n /jarvis/task
-> OpenJarvis callback
-> managed execution
-> verified terminal state
-> n8n /jarvis/result
-> downstream workflow
```

## Stable promotion gate

Promote rc3 to `2.0.0` only after the target Windows runtime completes:

1. OpenJarvis health = ok.
2. n8n container = reachable.
3. `GET /v1/autonomy/status` returns `ready=true`.
4. bundled smoke reaches `AUTONOMY_V2_SMOKE=PASS`.
5. result webhook acknowledges the terminal smoke result.
