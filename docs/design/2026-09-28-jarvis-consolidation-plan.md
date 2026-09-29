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
