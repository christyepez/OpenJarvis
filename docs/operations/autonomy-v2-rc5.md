# OpenJarvis Autonomy V2 — 2.0.0-rc5

## Release scope

This release candidate completes the autonomous execution loop and its n8n integration:

- goal planning;
- persistent task state;
- risk-based approval;
- n8n dispatch;
- managed-agent execution;
- bounded retries and recovery;
- cancellation and resume controls;
- startup recovery after process restart;
- bidirectional n8n result callbacks;
- one-command Windows bootstrap;
- readiness and smoke verification.

## Stable promotion gate

Promote to `2.0.0` only when the target Windows runtime reports all of the following:

```text
/health -> status=ok
/v1/autonomy/status -> ready=true
AUTONOMY_V2_RESULT_CALLBACK=PASS
AUTONOMY_V2_SMOKE=PASS
AUTONOMY_V2_BOOTSTRAP=PASS
```

The smoke must use real tools and must not modify files.
