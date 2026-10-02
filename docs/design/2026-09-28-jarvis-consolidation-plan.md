# OpenJarvis consolidation plan

## Decision

`christyepez/OpenJarvis` is the primary runtime and source of truth.
The other repositories are capability donors, not parallel runtimes:

- `CodexCommonAgents`: governance, project orchestration, Graphify, quality gates.
- `JARVIS`: HuggingGPT model-routing concepts, EasyTool concepts, TaskBench ideas.
- `jarvisAsistent`: operations-dashboard and live telemetry ideas only.

The consolidation must remain upstream-friendly: prefer adapters, policies, skills,
and extension points over invasive rewrites of OpenJarvis core.

## Non-negotiable execution policy

1. ChatGPT GPT-5.6 Sol is the principal implementer and reasoning coordinator when work is performed through ChatGPT.
2. Commander is the preferred execution plane for authorized computers.
3. Local/free/open-source models are preferred for delegated, repetitive, private, parallel, or low-cost execution.
4. Always search for a suitable local/free/open-source model before introducing a new paid service.
5. Codex and Commander are the currently pre-approved paid execution services.
6. ChatGPT GPT-5.6 Sol in the user's existing ChatGPT session does not imply approval to call a separately billed OpenAI API.
7. Every other paid model, API, SaaS, or tool requires explicit user approval before use.
## Routing order

Default execution preference:

1. ChatGPT GPT-5.6 Sol coordinates and implements the primary task in the interactive ChatGPT workflow.
2. Deterministic local tools and Commander execute concrete machine actions.
3. Already-installed local models handle suitable delegated work.
4. Free/open-source models that can run locally may be discovered and used for delegated work.
5. Free services/free tiers may be used when local execution is not suitable.
6. Codex may be used for approved coding workflows.
7. Any other paid provider requires explicit approval before use.

Cost policy must be enforced in code, not only in prompts.

## Target execution architecture

```text
Request
  -> Context Router
  -> Project/Personal/Professional/Knowledge memory
  -> Orchestrator
  -> Governance Policy
  -> Agent Router
  -> Model Router
  -> Skill/Tool Router
  -> Commander / MCP / local tools
  -> Quality gates
  -> Memory + learning
```
## Governance donor: CodexCommonAgents

Port or adapt the following capabilities:

- REUSE / EXTEND / ADAPT / CREATE / BLOCKED decisions.
- Project bootstrap and Project Orchestrator roles.
- Solution Architecture and Backend specialist roles.
- Graphify-first code-intelligence workflow.
- Docker/GHCR multi-machine governance.
- Security, API, observability, data, release and ownership rules.
- Anti-Slop and Thermos as executable quality gates.

The Markdown repository remains useful as policy source material, but critical
rules should progressively become executable policy checks and tests.

## Model intelligence donor: JARVIS

Do not copy legacy runtime dependencies. Re-implement the useful concepts using
current OpenJarvis abstractions:

- task planning;
- capability/model selection;
- expert-model execution;
- EasyTool-inspired compact tool discovery;
- TaskBench-inspired evaluation of routing and task automation.
## Operations donor: jarvisAsistent

Do not reuse its Webpack-specific architecture as the AI runtime. Reuse only
product ideas for a Jarvis Operations Dashboard:

- active agents and tasks;
- model/tool/skill selected;
- execution progress;
- CPU/RAM/GPU usage;
- latency, token and cost telemetry;
- errors, retries and quality-gate status;
- build/runtime health where relevant.

## Memory architecture

Project memory is important but must not reduce the general-purpose assistant.
Memory must support multiple domains: personal, professional, projects,
knowledge, finance, learning, communication and temporary context.

Authoritative project evidence remains Git, tests, ADRs and published artifacts;
memory is context, not a replacement for those sources of truth.
## Initial implementation waves

### Wave 1 - Foundation

- Add executable cost/provider governance.
- Preserve `before_tool_call` as the orchestrator enforcement hook.
- Add tests for local/free preference and paid approval requirements.
- Document consolidation boundaries and donor responsibilities.

### Wave 2 - Local model discovery

- Inventory installed engines/models.
- Discover compatible free/open-source candidates from curated sources.
- Filter by license, modality, RAM/VRAM, context and hardware.
- Benchmark candidates and retain task-specific scores.

### Wave 3 - Common-agent governance

- Convert the most important CodexCommonAgents rules into structured policies.
- Add Project Orchestrator, Graphify and specialist agent profiles.
- Add Anti-Slop and Thermos gates with evidence-based findings.
### Wave 4 - Execution plane

- Add Commander as a first-class authorized-machine execution adapter.
- Add machine routing for `trabajo` and `MarketingIndo` without hard-coding secrets.
- Keep MCP/connectors and local CLIs available through the normal tool layer.

### Wave 5 - Routing and evaluation

- Add capability-aware agent/model/skill routing.
- Add TaskBench-inspired JarvisBench suites.
- Measure task success, routing accuracy, latency, cost, retries and policy violations.

### Wave 6 - Operations dashboard

- Expose agent/task/model/skill/tool telemetry in the existing OpenJarvis frontend.
- Add live quality-gate, machine and execution-health views.

Each wave must remain independently testable and must not require a paid provider
other than the two pre-approved services unless the user explicitly approves it.


## Implementation status — 2026-10-01

The consolidation is now operational on `feature/jarvis-consolidation`.
OpenJarvis remains the only runtime/source of truth; donor repositories are
used for concepts and contracts rather than parallel execution.

| Wave | Status | Implemented evidence |
| --- | --- | --- |
| 1. Foundation | COMPLETE | provider/cost governance, paid-provider approval gates, governed tool hook |
| 2. Local model discovery | COMPLETE | local inventory, capability-aware routing, local/free preference and model roles |
| 3. Common-agent governance | COMPLETE | Project/Domain Orchestrators, Graphify skill, Qwen-MM, Anti-Slop, Thermos, quality pipelines |
| 4. Execution plane | COMPLETE | Commander machine routing, `trabajo`/MarketingIndo failover, bounded retry and evidence authorization |
| 5. Routing/evaluation | COMPLETE | capability/domain/model routing, JarvisBench metrics, compact EasyTool-inspired tool selection |
| 6. Operations dashboard | COMPLETE | models, agents/projects/tasks, machines, quality, tools, skills, safe next actions and retry audit evidence |

### Donor capability disposition

- `JARVIS`: ADAPT task/model-routing ideas, TaskBench concepts and EasyTool
  compact discovery; do not import its legacy runtime.
- `jarvisAsistent`: ADAPT dashboard/telemetry concepts only; do not reuse its
  Webpack-specific architecture.
- `CodexCommonAgents`: ADAPT governance, Graphify-first analysis, common-agent
  roles and evidence-based quality gates.


### Current validation baseline

Validation executed on `trabajo` through 2026-10-02:

- Governance + benchmark regression: **81 passed**.
- Task/project orchestration + templates + orchestrator regression: **145 passed**.
- Operations + managed shutdown/MCP regression: **26 passed**, no deprecation warnings.
- Frontend regression: **18 files / 102 passed**.
- Graphify portable runner: **4 passed**, Ruff **PASS**, runtime reports `graphify 0.9.63`.
- Production frontend build: **PASS**.
- Main frontend chunk reduced from **1,113.14 kB** to **453.54 kB**.
- Analytics now builds as a separate lazy chunk (**298.81 kB**); the ineffective dynamic-import warning is gone.
- Ruff on changed consolidation/server Python modules: **PASS**.
- `git diff --check main...HEAD`: **PASS**; `uv lock --check`: **PASS**.
- Distribution build: **PASS** for sdist and wheel.
- Clean Python 3.12 wheel install: **PASS** (`import openjarvis` and CLI entrypoint import).

Recent consolidation checkpoints include:

- `7053c0c1` — authorize exhausted worker retries via Operations.
- `a7e9ca79` — authorize exhausted retries from Operations UI.
- `5708d56f` — expose manual retry audit evidence.
- `3a2c5d74` — add compact tool discovery.
- `3e68d076` — enable compact tool catalogs for orchestrators.

### Non-blocking technical debt

- The managed FastAPI shutdown now uses lifespan instead of deprecated `on_event`.
- Frontend analytics and secondary routes are lazy-loaded; the main production
  chunk is below 500 kB and the ineffective dynamic-import warning is resolved.
- Starlette `TestClient` now uses the dev-only `httpx2` dependency, removing
  the previous fallback-to-`httpx` deprecation warning from server test runs.
- GitHub Actions workflows exist in `main`, but this public fork has not enabled
  fork workflows yet; enable Actions on the fork before relying on remote CI.
