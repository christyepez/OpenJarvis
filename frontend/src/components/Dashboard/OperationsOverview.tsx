import { useEffect, useState } from 'react';
import {
  fetchOperationsStatus,
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
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-text)' }}>
            <span>{status.machines.primary.name}</span>
            <Badge>{status.machines.primary.status}</Badge>
          </div>
          {status.machines.fallbacks.map((machine) => (
            <div
              key={machine.name}
              className="flex items-center gap-2 text-xs mt-2"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              <span>fallback → {machine.name}</span>
              <Badge>{machine.status}</Badge>
            </div>
          ))}
        </Card>

        <Card title="Quality pipeline">
          <div className="flex flex-wrap gap-1.5">
            {status.quality_pipeline.map((stage, index) => (
              <Badge key={stage}>{index + 1}. {stage}</Badge>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 mt-3">
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
    </div>
  );
}
