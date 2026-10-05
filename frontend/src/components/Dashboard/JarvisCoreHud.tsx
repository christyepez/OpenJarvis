import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { fetchOperationsStatus, type OperationsStatus } from '../../lib/api';

type JarvisCoreHudProps = {
  compact?: boolean;
};

function StatusPill({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={`jarvis-status-pill ${ok ? 'is-ok' : 'is-warn'}`}>
      <span className="jarvis-status-dot" />
      {label}
    </span>
  );
}

export function JarvisCoreHud({ compact = false }: JarvisCoreHudProps) {
  const navigate = useNavigate();
  const [status, setStatus] = useState<OperationsStatus | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      fetchOperationsStatus()
        .then((next) => {
          if (!active) return;
          setStatus(next);
          setError(false);
        })
        .catch(() => {
          if (active) setError(true);
        });
    };

    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const operational = Boolean(
    status?.runtime.available &&
      status?.execution.commander_connected &&
      status?.memory.enabled,
  );
  const agentsRunning = status?.agents.by_status?.running ?? 0;
  const selectedMachine = status?.machines.selected ?? status?.machines.primary.name ?? 'unassigned';
  const memoryDocs = status?.memory.documents ?? 0;
  const model = status?.runtime.model || 'detecting';
  const coreLabel = error ? 'LINK DEGRADED' : operational ? 'JARVIS ONLINE' : 'INITIALIZING';

  const orbitItems = useMemo(
    () => [
      { label: 'MODEL', value: model },
      { label: 'MACHINE', value: selectedMachine },
      { label: 'MEMORY', value: status?.memory.backend || 'offline' },
      { label: 'MCP', value: String(status?.tools.mcp_count ?? 0) },
    ],
    [model, selectedMachine, status],
  );

  if (compact) {
    return (
      <section className="jarvis-compact-shell" aria-label="Jarvis runtime status">
        <div className="jarvis-compact-core" aria-hidden="true">
          <span className="jarvis-core-pulse" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="jarvis-kicker">JARVIS // LIVE CORE</div>
          <div className="jarvis-compact-title">{coreLabel}</div>
          <div className="jarvis-compact-meta">
            {model} · {selectedMachine} · {memoryDocs} memories
          </div>
        </div>
        <div className="hidden lg:flex items-center gap-2">
          <StatusPill label="COMMANDER" ok={Boolean(status?.execution.commander_connected)} />
          <StatusPill label="MEMORY" ok={Boolean(status?.memory.enabled)} />
          <StatusPill label="RUNTIME" ok={Boolean(status?.runtime.available)} />
        </div>
        <button className="jarvis-hud-button" onClick={() => navigate('/dashboard')}>
          OPEN HUD
        </button>
      </section>
    );
  }

  return (
    <section className="jarvis-hud-shell" aria-label="Jarvis visual command core">
      <div className="jarvis-hud-scan" aria-hidden="true" />
      <div className="jarvis-hud-corner tl" aria-hidden="true" />
      <div className="jarvis-hud-corner tr" aria-hidden="true" />
      <div className="jarvis-hud-corner bl" aria-hidden="true" />
      <div className="jarvis-hud-corner br" aria-hidden="true" />

      <div className="jarvis-hud-topline">
        <div>
          <div className="jarvis-kicker">OPENJARVIS // PERSONAL AI COMMAND SYSTEM</div>
          <h1 className="jarvis-hud-title">{coreLabel}<span className="hud-caret" /></h1>
        </div>
        <div className="jarvis-hud-badges">
          <StatusPill label="RUNTIME" ok={Boolean(status?.runtime.available)} />
          <StatusPill label="COMMANDER" ok={Boolean(status?.execution.commander_connected)} />
          <StatusPill label="MEMORY" ok={Boolean(status?.memory.enabled)} />
        </div>
      </div>

      <div className="jarvis-hud-grid">
        <div className="jarvis-side-stack left">
          <div className="jarvis-data-card">
            <span>PRIMARY MODEL</span>
            <strong>{model}</strong>
            <small>{status?.runtime.engine || 'engine pending'}</small>
          </div>
          <div className="jarvis-data-card">
            <span>EXECUTION NODE</span>
            <strong>{selectedMachine}</strong>
            <small>{status?.machines.signal || 'awaiting signal'}</small>
          </div>
          <div className="jarvis-data-card">
            <span>ACTIVE AGENTS</span>
            <strong>{agentsRunning}</strong>
            <small>{status?.agents.total ?? 0} registered</small>
          </div>
        </div>

        <div className="jarvis-core-stage">
          <div className="jarvis-core-orbit orbit-a" aria-hidden="true" />
          <div className="jarvis-core-orbit orbit-b" aria-hidden="true" />
          <div className="jarvis-core-orbit orbit-c" aria-hidden="true" />
          <div className="jarvis-core-crosshair horizontal" aria-hidden="true" />
          <div className="jarvis-core-crosshair vertical" aria-hidden="true" />
          <div className={`jarvis-core-reactor ${operational ? 'is-online' : ''}`}>
            <div className="jarvis-core-reactor-inner">
              <span className="jarvis-core-symbol">J</span>
              <span className="jarvis-core-state">{operational ? 'ONLINE' : 'SYNC'}</span>
            </div>
          </div>
          {orbitItems.map((item, index) => (
            <div className={`jarvis-orbit-label orbit-label-${index + 1}`} key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>

        <div className="jarvis-side-stack right">
          <div className="jarvis-data-card">
            <span>MEMORY MATRIX</span>
            <strong>{memoryDocs}</strong>
            <small>{status?.memory.backend || 'offline'} documents</small>
          </div>
          <div className="jarvis-data-card">
            <span>MCP TOOLS</span>
            <strong>{status?.tools.mcp_count ?? 0}</strong>
            <small>{status?.execution.preferred_plane || 'commander'} plane</small>
          </div>
          <div className="jarvis-data-card">
            <span>PROJECTS</span>
            <strong>{status?.projects.total ?? 0}</strong>
            <small>{status?.quality.total ?? 0} quality pipelines</small>
          </div>
        </div>
      </div>

      <div className="jarvis-hud-footer">
        <div className="jarvis-signal-line">
          <span className="hud-heartbeat" />
          <span>{error ? 'Operations link degraded' : 'Neural telemetry synchronized'}</span>
        </div>
        <div className="jarvis-actions">
          <button className="jarvis-hud-button secondary" onClick={() => navigate('/')}>CHAT</button>
          <button className="jarvis-hud-button" onClick={() => navigate('/agents')}>AGENTS</button>
        </div>
      </div>
    </section>
  );
}
