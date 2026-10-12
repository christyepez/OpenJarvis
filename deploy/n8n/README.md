# OpenJarvis + n8n (Autonomy V2)

This folder contains the local n8n runtime used by OpenJarvis for asynchronous workflows.

## Start n8n

1. Copy `.env.example` to `.env`.
2. If OpenJarvis API authentication is enabled, set `OPENJARVIS_API_KEY`.
3. Start the container:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-n8n.ps1
```

n8n will be available at:

```text
http://127.0.0.1:5678
```

## Import the first workflow

Import:

```text
workflows/jarvis-task-dispatcher.json
```

Activate **Jarvis Task Dispatcher**.

The production webhook becomes:

```text
http://127.0.0.1:5678/webhook/jarvis/task
```

Configure OpenJarvis before starting the API:

```powershell
$env:OPENJARVIS_N8N_WEBHOOK_URL = "http://127.0.0.1:5678/webhook/jarvis/task"
```

When authentication is enabled, configure the same OpenJarvis API key in
`deploy/n8n/.env`.

## Current round trip

The first workflow intentionally proves only the transport checkpoint:

```text
OpenJarvis
  -> POST /webhook/jarvis/task
  -> n8n returns accepted + executionId
  -> OpenJarvis persists the task
  -> n8n POSTs /v1/autonomy/callback
  -> task becomes waiting
  -> checkpoint = n8n-dispatcher-ready
```

The next Autonomy V2 checkpoint connects the n8n dispatcher to the Jarvis
planner/executor so the task moves from `waiting` to `running` and eventually
`completed` or `failed`.

## OpenJarvis endpoints

```text
POST /v1/autonomy/tasks
POST /v1/autonomy/callback
GET  /v1/autonomy/tasks/{taskId}
GET  /v1/autonomy/tasks
```

Example task:

```json
{
  "goal": "Review OpenJarvis, run the tests and prepare the next safe change",
  "project": "OpenJarvis",
  "workflow": "auto",
  "context": {
    "branch": "main"
  },
  "approval": "risk_based"
}
```
