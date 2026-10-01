import { useEffect, useState } from 'react';
import {
  executeOperationsProjectNextAction,
  executeOperationsTaskNextAction,
  fetchOperationsStatus,
  probeOperationsMachines,
  type OperationsStatus,
} from '../../lib/api';

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px]"
      style={{
        border: '1px solid var(--color-border)',
        color: 'var(--color-text-secondary)',
        background: 'color-mix(in srgb, var(--color-surface) 88%, transparent)',
      }}
    >
      {children}
    </span>
  );
}

export function ModelRoleSummary({
  roleModels,
}: {
  roleModels: OperationsStatus['runtime']['role_models'];
}) {
  const roles = [
    ['general', roleModels.general],
    ['coding', roleModels.coding],
    ['multimodal', roleModels.multimodal],
  ] as const;

  return (
    <div className="space-y-2">
      {roles.map(([role, model]) => (
        <div key={role} className="flex items-center justify-between gap-3 text-xs">
          <span
            className="capitalize"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {role}
          </span>
          <Badge>{model || 'unassigned'}</Badge>
        </div>
      ))}
    </div>
  );
}

export function MachineRoutingSummary({
  execution,
  machines,
  onProbe,
  probing = false,
}: {
  execution: OperationsStatus['execution'];
  machines: OperationsStatus['machines'];
  onProbe?: () => void;
  probing?: boolean;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span style={{ color: 'var(--color-text)' }}>
          {machines.selected || machines.primary.name}
        </span>
        <Badge>
          {machines.selected
            ? `selected · ${machines.signal}`
            : `configured · ${machines.signal}`}
        </Badge>
      </div>
      <div className="flex items-center justify-between gap-2 text-xs">
        <span style={{ color: 'var(--color-text-secondary)' }}>
          {machines.primary.name}
        </span>
        <Badge>{machines.primary.status}</Badge>
      </div>
      {machines.fallbacks.map((machine) => (
        <div
          key={machine.name}
          className="flex items-center justify-between gap-2 text-xs"
        >
          <span style={{ color: 'var(--color-text-secondary)' }}>
            fallback → {machine.name}
          </span>
          <div className="flex flex-wrap gap-1">
            <Badge>{machine.status}</Badge>
            {machine.docker_available ? <Badge>docker</Badge> : null}
            {machine.gpu_available ? <Badge>gpu</Badge> : null}
          </div>
        </div>
      ))}
      <div className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
        plane: {execution.preferred_plane} · commander:{' '}
        {execution.commander_connected ? 'connected' : 'not detected'}
      </div>
      {onProbe ? (
        <button
          type="button"
          className="rounded-full px-2 py-1 text-[11px] disabled:opacity-50"
          style={{
            border: '1px solid var(--color-border)',
            color: 'var(--color-text-secondary)',
            background: 'var(--color-surface)',
          }}
          disabled={probing}
          onClick={onProbe}
        >
          {probing ? 'Refreshing…' : 'Refresh machines'}
        </button>
      ) : null}
    </div>
  );
}

export function AgentRoutingSummary({
  agents,
  onNextAction,
  busyTaskKey = '',
}: {
  agents: OperationsStatus['agents']['agents'];
  onNextAction?: (taskKey: string) => void;
  busyTaskKey?: string;
}) {
  if (!agents.length) {
    return (
      <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
        No managed agents
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {agents.slice(0, 5).map((agent) => (
        <div key={agent.id} className="flex items-center justify-between gap-3 text-xs">
          <div className="min-w-0">
            <div
              className="truncate font-medium"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {agent.name || agent.id}
            </div>
            <div
              className="truncate"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              {[
                agent.project_stream || agent.domain,
                agent.capability || 'general',
                agent.model_policy || 'default',
              ]
                .filter(Boolean)
                .join(' · ')}
            </div>
            {agent.domain_task_key ? (
              <>
                <div
                  className="truncate max-w-[360px] mt-0.5"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  task: {agent.domain_task_key}
                </div>
                <div
                  className="truncate max-w-[360px] mt-0.5"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  next: {agent.domain_next_action}
                </div>
              </>
            ) : null}
            {agent.domain_handoff_ready && agent.domain_result ? (
              <div
                className="truncate max-w-[360px] mt-0.5"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                {agent.domain_result}
              </div>
            ) : null}
            {agent.domain_quality_stages.length ? (
              <div
                className="truncate max-w-[360px] mt-0.5"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                {agent.domain_quality_stages
                  .map((stage) => `${stage.stage}: ${stage.status}`)
                  .join(' · ')}
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap justify-end gap-1">
            {agent.domain_handoff_ready ? <Badge>handoff ready</Badge> : null}
            {agent.domain_task_key ? (
              <Badge>task: {agent.domain_task_state}</Badge>
            ) : null}
            {agent.domain ? (
              <Badge>quality: {agent.domain_quality_status}</Badge>
            ) : null}
            {agent.domain_next_action.startsWith('resolve-quality:') ? (
              <Badge>evidence required</Badge>
            ) : null}
            {onNextAction &&
            agent.domain_task_key &&
            /^(advance|retry):/.test(agent.domain_next_action) ? (
              <button
                type="button"
                className="rounded-full px-2 py-0.5 text-[11px] disabled:opacity-50"
                style={{
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-secondary)',
                  background: 'var(--color-surface)',
                }}
                disabled={busyTaskKey === agent.domain_task_key}
                onClick={() => onNextAction(agent.domain_task_key)}
              >
                {busyTaskKey === agent.domain_task_key ? 'Running…' : 'Run next'}
              </button>
            ) : null}
            <Badge>{agent.routed_model || 'unassigned'}</Badge>
          </div>
        </div>
      ))}
    </div>
  );
}

export function MemorySummary({
  memory,
}: {
  memory: OperationsStatus['memory'];
}) {
  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <div className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>
          {memory.backend || 'disabled'}
        </div>
        <Badge>{memory.enabled ? 'enabled' : 'disabled'}</Badge>
      </div>
      <div className="text-xs mt-2" style={{ color: 'var(--color-text-tertiary)' }}>
        {memory.documents === null
          ? 'Document count unavailable'
          : memory.documents + ' stored documents'}
      </div>
    </>
  );
}

export function ProjectBoardSummary({
  projects,
  onNextAction,
  busyProjectKey = '',
  machineAvailable = true,
}: {
  projects: OperationsStatus['projects'];
  onNextAction?: (projectKey: string) => void;
  busyProjectKey?: string;
  machineAvailable?: boolean;
}) {
  if (!projects.projects.length) {
    return (
      <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
        No bootstrapped projects
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {projects.projects.slice(0, 3).map((project) => (
        <div key={project.project_key}>
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div
                className="truncate text-xs font-medium"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {project.name || project.project_key}
              </div>
              {project.repository ? (
                <div
                  className="truncate text-[11px]"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  {project.repository}
                </div>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-1">
              <Badge>{project.status}</Badge>
              <Badge>quality: {project.quality_status}</Badge>
            </div>
          </div>
          <div className="flex flex-wrap gap-1 mt-1.5">
            {project.ready_streams.length ? (
              <Badge>READY: {project.ready_streams.length}</Badge>
            ) : null}
            {project.active_streams.length ? (
              <Badge>ACTIVE: {project.active_streams.length}</Badge>
            ) : null}
            {project.handoff_ready_streams.length ? (
              <Badge>REVIEW: {project.handoff_ready_streams.length}</Badge>
            ) : null}
            {project.failed_streams.length ? (
              <Badge>ERROR: {project.failed_streams.length}</Badge>
            ) : null}
            {project.blocked_streams.length ? (
              <Badge>BLOCKED: {project.blocked_streams.length}</Badge>
            ) : null}
            {project.done_streams.length ? (
              <Badge>DONE: {project.done_streams.length}</Badge>
            ) : null}
          </div>
          {project.next_action ? (
            <div
              className="text-[11px] mt-1.5"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              next: {project.next_action}
            </div>
          ) : null}
          <div className="flex flex-wrap gap-1 mt-1.5">
            {project.next_action.startsWith('resolve-quality:') ? (
              <Badge>evidence required</Badge>
            ) : null}
            {project.handoff_ready_streams.length ? (
              <Badge>handoff review required</Badge>
            ) : null}
            {project.runtime_machines.length > 0 && !machineAvailable ? (
              <Badge>runtime unavailable</Badge>
            ) : null}
            {onNextAction &&
            (project.runtime_machines.length === 0 || machineAvailable) &&
            (project.ready_streams.length > 0 ||
              project.next_action.startsWith('retry-workers:') ||
              project.next_action === 'start-quality-pipeline' ||
              project.next_action.startsWith('advance-quality:')) ? (
              <button
                type="button"
                className="rounded-full px-2 py-0.5 text-[11px] disabled:opacity-50"
                style={{
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-secondary)',
                  background: 'var(--color-surface)',
                }}
                disabled={busyProjectKey === project.project_key}
                onClick={() => onNextAction(project.project_key)}
              >
                {busyProjectKey === project.project_key ? 'Running…' : 'Run next'}
              </button>
            ) : null}
          </div>
          {project.quality_stages.length ? (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {project.quality_stages.map((stage) => (
                <Badge key={stage.task_id}>
                  {stage.stage}: {stage.status}
                </Badge>
              ))}
            </div>
          ) : null}
          <div className="space-y-1.5 mt-1.5">
            {project.streams.map((stream) => (
              <div key={stream.task_id} className="flex flex-wrap items-center gap-1">
                <Badge>
                  {stream.wave}.{stream.stream}: {stream.status}
                </Badge>
                {stream.branch ? <Badge>{stream.branch}</Badge> : null}
                {stream.runtime_machine ? (
                  <Badge>machine: {stream.runtime_machine}</Badge>
                ) : null}
                {stream.runtime_machine_status ? (
                  <Badge>runtime: {stream.runtime_machine_status}</Badge>
                ) : null}
                {stream.handoff_ready ? (
                  <Badge>handoff ready: {stream.findings_count}</Badge>
                ) : null}
                {stream.worker_status ? (
                  <Badge>{stream.worker_status}</Badge>
                ) : null}
                {stream.worker_agent_id ? (
                  <span
                    className="text-[10px]"
                    style={{ color: 'var(--color-text-tertiary)' }}
                  >
                    worker: {stream.worker_agent_id}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
          {project.runtime_machines.length ? (
            <div
              className="text-[11px] mt-1.5"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              runtime: {project.runtime_machines.join(', ')}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}


export function QualityRunSummary({
  quality,
}: {
  quality: OperationsStatus['quality'];
}) {
  if (!quality.pipelines.length) {
    return (
      <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
        No quality runs
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {quality.pipelines.slice(0, 3).map((pipeline) => (
        <div key={pipeline.pipeline_id}>
          <div className="flex items-center justify-between gap-3">
            <div
              className="truncate text-xs font-medium"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {pipeline.objective || pipeline.pipeline_id}
            </div>
            <Badge>{pipeline.status}</Badge>
          </div>
          <div className="flex flex-wrap gap-1 mt-1.5">
            {pipeline.stages.map((stage) => (
              <Badge key={stage.task_id}>
                {stage.stage}: {stage.status}
              </Badge>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}


function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="rounded-xl p-4"
      style={{
        border: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
      }}
    >
      <div
        className="text-xs font-medium uppercase tracking-wide mb-3"
        style={{ color: 'var(--color-text-tertiary)' }}
      >
        {title}
      </div>
      {children}
    </section>
  );
}
export function OperationsOverview() {
  const [status, setStatus] = useState<OperationsStatus | null>(null);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyTaskKey, setBusyTaskKey] = useState('');
  const [busyProjectKey, setBusyProjectKey] = useState('');
  const [probingMachines, setProbingMachines] = useState(false);

  useEffect(() => {
    let mounted = true;
    const refresh = async () => {
      try {
        const value = await fetchOperationsStatus();
        if (mounted) {
          setStatus(value);
          setError('');
        }
      } catch (e) {
        if (mounted) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    };
    void refresh();
    const timer = setInterval(refresh, 15000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  const runNextAction = async (taskKey: string) => {
    setBusyTaskKey(taskKey);
    setActionError('');
    try {
      await executeOperationsTaskNextAction(taskKey);
      setStatus(await fetchOperationsStatus());
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyTaskKey('');
    }
  };

  const runProjectNextAction = async (projectKey: string) => {
    setBusyProjectKey(projectKey);
    setActionError('');
    try {
      await executeOperationsProjectNextAction(projectKey);
      setStatus(await fetchOperationsStatus());
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyProjectKey('');
    }
  };

  const refreshMachines = async () => {
    setProbingMachines(true);
    setActionError('');
    try {
      await probeOperationsMachines();
      setStatus(await fetchOperationsStatus());
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setProbingMachines(false);
    }
  };

  if (!status) {
    return (
      <div
        className="rounded-xl p-4 text-sm mb-4"
        style={{
          border: '1px solid var(--color-border)',
          color: error ? 'var(--color-error)' : 'var(--color-text-secondary)',
        }}
      >
        {error || 'Loading operations status…'}
      </div>
    );
  }

  const activeAgents = Object.entries(status.agents.by_status)
    .filter(([name]) => !['archived', 'paused'].includes(name))
    .reduce((sum, [, value]) => sum + value, 0);
  return (
    <div className="mb-6">
      {actionError ? (
        <div
          className="rounded-xl p-3 text-xs mb-3"
          style={{
            border: '1px solid var(--color-border)',
            color: 'var(--color-error)',
          }}
        >
          {actionError}
        </div>
      ) : null}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 mb-3">
        <Card title="Primary implementer">
          <div className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>
            {status.primary_implementer}
          </div>
          <div className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
            Interactive reasoning coordinator
          </div>
        </Card>

        <Card title="Runtime">
          <div className="flex items-center justify-between gap-2">
            <div className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>
              {status.runtime.engine || 'unknown'}
            </div>
            <Badge>
              {status.runtime.available === true
                ? 'online'
                : status.runtime.available === false
                  ? 'offline'
                  : 'unknown'}
            </Badge>
          </div>
          <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            {status.runtime.model || 'No active model'}
          </div>
        </Card>

        <Card title="Local models">
          <div className="text-2xl font-semibold" style={{ color: 'var(--color-text)' }}>
            {status.runtime.local_models.length}
          </div>
          <div className="flex flex-wrap gap-1 mt-2">
            {status.runtime.local_models.slice(0, 3).map((model) => (
              <Badge key={model}>{model}</Badge>
            ))}
          </div>
        </Card>

        <Card title="Managed agents">
          <div className="text-2xl font-semibold" style={{ color: 'var(--color-text)' }}>
            {status.agents.total}
          </div>
          <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            {activeAgents} active/available
          </div>
          <div className="flex flex-wrap gap-1 mt-2">
            {Object.entries(status.agents.by_domain)
              .slice(0, 4)
              .map(([domain, count]) => (
                <Badge key={domain}>{domain}: {count}</Badge>
              ))}
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        <Card title="Model roles">
          <ModelRoleSummary roleModels={status.runtime.role_models} />
        </Card>

        <Card title="Governance">
          <div className="flex flex-wrap gap-1.5">
            <Badge>{status.governance.prefer_local ? 'local-first' : 'local optional'}</Badge>
            <Badge>{status.governance.prefer_free ? 'free-first' : 'free optional'}</Badge>
            <Badge>
              {status.governance.require_approval_for_unapproved_paid
                ? 'paid approval required'
                : 'paid approval disabled'}
            </Badge>
          </div>
          <div className="text-xs mt-3" style={{ color: 'var(--color-text-tertiary)' }}>
            Approved: {status.governance.approved_paid.join(', ') || 'none'}
          </div>
        </Card>

        <Card title="Machine routing">
          <MachineRoutingSummary
            execution={status.execution}
            machines={status.machines}
            probing={probingMachines}
            onProbe={() => {
              void refreshMachines();
            }}
          />
        </Card>

        <Card title="Quality pipeline">
          <div className="flex flex-wrap gap-1.5">
            {status.quality_pipeline.map((stage, index) => (
              <Badge key={stage}>{index + 1}. {stage}</Badge>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 mt-3">
        <Card title="Memory">
          <MemorySummary memory={status.memory} />
        </Card>

        <Card title="Tasks">
          <div className="text-2xl font-semibold" style={{ color: 'var(--color-text)' }}>
            {status.agents.tasks.total}
          </div>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {Object.entries(status.agents.tasks.by_status).map(([name, count]) => (
              <Badge key={name}>{name}: {count}</Badge>
            ))}
          </div>
        </Card>

        <Card title="Tools / MCP">
          <div className="flex items-end gap-5">
            <div>
              <div className="text-xl font-semibold" style={{ color: 'var(--color-text)' }}>
                {status.tools.native_count}
              </div>
              <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                native
              </div>
            </div>
            <div>
              <div className="text-xl font-semibold" style={{ color: 'var(--color-text)' }}>
                {status.tools.mcp_count}
              </div>
              <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                MCP
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-1 mt-2">
            {status.tools.mcp.slice(0, 4).map((tool) => (
              <Badge key={tool}>{tool}</Badge>
            ))}
          </div>
        </Card>

        <Card title="Skills">
          <div className="text-2xl font-semibold" style={{ color: 'var(--color-text)' }}>
            {status.skills.count}
          </div>
          <div className="flex flex-wrap gap-1 mt-2">
            {status.skills.items.slice(0, 5).map((skill) => (
              <Badge key={skill}>{skill}</Badge>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 mt-3">
        <Card title="Projects / execution boards">
          <ProjectBoardSummary
            projects={status.projects}
            busyProjectKey={busyProjectKey}
            machineAvailable={status.machines.selected !== null}
            onNextAction={(projectKey) => {
              void runProjectNextAction(projectKey);
            }}
          />
        </Card>
        <Card title="Agent routing">
          <AgentRoutingSummary
            agents={status.agents.agents}
            busyTaskKey={busyTaskKey}
            onNextAction={(taskKey) => {
              void runNextAction(taskKey);
            }}
          />
        </Card>
        <Card title="Quality runs">
          <QualityRunSummary quality={status.quality} />
        </Card>
      </div>
    </div>
  );
}
