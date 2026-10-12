# OpenJarvis Autonomy V2 — 2.0.0-rc2

## Included capabilities

- Persistent SQLite TaskStore with resumable states.
- n8n task dispatch and callback contract.
- Managed-agent execution isolated per autonomy task.
- Planner with code/data/general workflows.
- Risk-based approval gateway.
- Startup recovery for running/waiting tasks.
- n8n Docker deployment, import/publish helper and smoke script.
- Autonomy readiness endpoint at `GET /v1/autonomy/status`.

## Runtime readiness contract

A runtime is considered ready when:

1. `OPENJARVIS_N8N_WEBHOOK_URL` is configured and n8n is available.
2. The OpenJarvis managed-agent runtime is active.
3. `GET /v1/autonomy/status` returns `"ready": true`.
4. `deploy/n8n/smoke-autonomy.ps1` reaches `AUTONOMY_V2_SMOKE=PASS`.

## Safe smoke objective

The bundled smoke test only asks Jarvis to inspect the OpenJarvis directory with real tools.
It must not modify files. This validates:

```text
create task
-> planner
-> approval assessment
-> n8n dispatch
-> callback
-> managed execution
-> tool evidence
-> verified completion
-> persistent result
```

## Promotion rule

`2.0.0-rc2` may be promoted to `2.0.0` after the real Windows + Docker n8n
smoke completes successfully on the target runtime.
