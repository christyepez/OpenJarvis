# OpenJarvis Autonomy V2 — 2.0.0-rc6

## Delta from rc5

- Voice autonomous objectives now route through the persistent Autonomy V2 plane when the runtime is fully ready.
- Voice tasks carry workspace, runtime device, objective-specific MCP allowlist and completion evidence requirements.
- Sensitive voice objectives remain subject to the risk-based approval gateway.
- If Autonomy V2 is not fully ready, voice falls back to the proven legacy managed-agent runner.
- The focused Autonomy V2 CI gate now includes `voice_control.py` and its speech tests.
- Stable promotion now requires both Autonomy V2 and voice autonomy tests/lint.

## Stable promotion gate

Promote to `2.0.0` only after the target Windows runtime reports:

```text
/health -> status=ok
/v1/autonomy/status -> ready=true
AUTONOMY_V2_RESULT_CALLBACK=PASS
AUTONOMY_V2_SMOKE=PASS
AUTONOMY_V2_BOOTSTRAP=PASS
```

and the focused Autonomy V2 + voice tests and lint pass.
