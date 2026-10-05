import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { fetchOperationsStatus, type OperationsStatus } from '../../lib/api';
import { useAppStore } from '../../lib/store';
import { useTtsStore } from '../../lib/tts';

type JarvisCoreHudProps = {
  compact?: boolean;
};

type VoiceSignalState = 'idle' | 'recording' | 'transcribing';
type CoreMode = 'offline' | 'online' | 'listening' | 'thinking' | 'executing' | 'speaking';

function StatusPill({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={`jarvis-status-pill ${ok ? 'is-ok' : 'is-warn'}`}>
      <span className="jarvis-status-dot" />
      {label}
    </span>
  );
}

function Waveform({ active }: { active: boolean }) {
  return (
    <div className={`jarvis-waveform ${active ? 'is-active' : ''}`} aria-hidden="true">
      {Array.from({ length: 18 }).map((_, index) => (
        <span key={index} style={{ animationDelay: `${index * -70}ms` }} />
      ))}
    </div>
  );
}

export function JarvisCoreHud({ compact = false }: JarvisCoreHudProps) {
  const navigate = useNavigate();
  const shellRef = useRef<HTMLElement | null>(null);
  const [status, setStatus] = useState<OperationsStatus | null>(null);
  const [error, setError] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceSignalState>('idle');
  const [voiceAvailable, setVoiceAvailable] = useState(false);
  const [ambient, setAmbient] = useState(false);
  const [wakeEnabled, setWakeEnabled] = useState(
    () => localStorage.getItem('jarvis-wake-enabled') === '1',
  );
  const [wakeSupported, setWakeSupported] = useState(false);
  const isStreaming = useAppStore((s) => s.streamState.isStreaming);
  const streamPhase = useAppStore((s) => s.streamState.phase);
  const activeToolCalls = useAppStore((s) => s.streamState.activeToolCalls);
  const ttsState = useTtsStore((s) => s.state);

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

  useEffect(() => {
    const onVoiceState = (event: Event) => {
      const detail = (event as CustomEvent<{ state?: VoiceSignalState; available?: boolean }>).detail;
      if (detail?.state) setVoiceState(detail.state);
      if (typeof detail?.available === 'boolean') setVoiceAvailable(detail.available);
    };
    window.addEventListener('jarvis:voice-state', onVoiceState);
    return () => window.removeEventListener('jarvis:voice-state', onVoiceState);
  }, []);

  useEffect(() => {
    const onFullscreen = () => setAmbient(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', onFullscreen);
    return () => document.removeEventListener('fullscreenchange', onFullscreen);
  }, []);

  useEffect(() => {
    const speechWindow = window as unknown as {
      SpeechRecognition?: new () => {
        continuous: boolean;
        interimResults: boolean;
        lang: string;
        start: () => void;
        stop: () => void;
        onresult: ((event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null;
        onend: (() => void) | null;
        onerror: (() => void) | null;
      };
      webkitSpeechRecognition?: new () => {
        continuous: boolean;
        interimResults: boolean;
        lang: string;
        start: () => void;
        stop: () => void;
        onresult: ((event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null;
        onend: (() => void) | null;
        onerror: (() => void) | null;
      };
    };
    const Ctor = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
    setWakeSupported(Boolean(Ctor));
    if (!wakeEnabled || !Ctor) return;

    let active = true;
    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = navigator.language || 'es-EC';

    recognition.onresult = (event) => {
      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (!result?.isFinal) continue;
        const transcript = result[0]?.transcript?.trim() ?? '';
        const match = transcript.match(/\bjarvis\b[,:]?\s*(.*)$/i);
        if (!match) continue;
        const command = match[1]?.trim() ?? '';
        window.dispatchEvent(new CustomEvent('jarvis:wake', { detail: { transcript } }));
        window.dispatchEvent(new CustomEvent('jarvis:wake-command', { detail: { command } }));
        navigate('/');
      }
    };
    recognition.onerror = () => {
      if (active) setWakeEnabled(false);
    };
    recognition.onend = () => {
      if (!active) return;
      window.setTimeout(() => {
        try {
          recognition.start();
        } catch {
          // Browser may still be finalizing the previous recognition cycle.
        }
      }, 250);
    };

    try {
      recognition.start();
    } catch {
      setWakeEnabled(false);
    }

    return () => {
      active = false;
      recognition.onend = null;
      recognition.stop();
    };
  }, [wakeEnabled, navigate]);

  useEffect(() => {
    localStorage.setItem('jarvis-wake-enabled', wakeEnabled ? '1' : '0');
  }, [wakeEnabled]);

  const operational = Boolean(
    status?.runtime.available &&
      status?.execution.commander_connected &&
      status?.memory.enabled,
  );
  const agentsRunning = status?.agents.by_status?.running ?? 0;
  const selectedMachine = status?.machines.selected ?? status?.machines.primary.name ?? 'unassigned';
  const memoryDocs = status?.memory.documents ?? 0;
  const model = status?.runtime.model || 'detecting';

  let mode: CoreMode = error || !operational ? 'offline' : 'online';
  if (voiceState === 'recording') mode = 'listening';
  else if (voiceState === 'transcribing') mode = 'thinking';
  else if (ttsState === 'speaking' || ttsState === 'loading') mode = 'speaking';
  else if (isStreaming && (activeToolCalls?.length ?? 0) > 0) mode = 'executing';
  else if (isStreaming || agentsRunning > 0) mode = 'thinking';

  const labels: Record<CoreMode, string> = {
    offline: error ? 'LINK DEGRADED' : 'INITIALIZING',
    online: 'JARVIS ONLINE',
    listening: 'LISTENING',
    thinking: 'THINKING',
    executing: 'EXECUTING',
    speaking: 'SPEAKING',
  };
  const shortLabels: Record<CoreMode, string> = {
    offline: 'SYNC',
    online: 'ONLINE',
    listening: 'LISTEN',
    thinking: 'THINK',
    executing: 'EXEC',
    speaking: 'VOICE',
  };
  const coreLabel = labels[mode];

  const orbitItems = useMemo(
    () => [
      { label: 'MODEL', value: model },
      { label: 'MACHINE', value: selectedMachine },
      { label: 'MEMORY', value: status?.memory.backend || 'offline' },
      { label: 'MCP', value: String(status?.tools.mcp_count ?? 0) },
    ],
    [model, selectedMachine, status],
  );

  const toggleFullscreen = async () => {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
      return;
    }
    await shellRef.current?.requestFullscreen?.();
  };

  const activityLabel =
    mode === 'listening'
      ? 'Microphone channel open'
      : mode === 'speaking'
        ? 'Voice synthesis active'
        : mode === 'executing'
          ? activeToolCalls?.[0]?.tool
            ? `Executing ${activeToolCalls[0].tool}`
            : 'Executing tool workflow'
          : mode === 'thinking'
            ? streamPhase || (agentsRunning > 0 ? `${agentsRunning} agent(s) active` : 'Inference in progress')
            : error
              ? 'Operations link degraded'
              : 'Neural telemetry synchronized';

  if (compact) {
    return (
      <section className={`jarvis-compact-shell mode-${mode}`} aria-label="Jarvis runtime status">
        <div className="jarvis-compact-core" aria-hidden="true">
          <span className="jarvis-core-pulse" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="jarvis-kicker">JARVIS // LIVE CORE</div>
          <div className="jarvis-compact-title">{coreLabel}</div>
          <div className="jarvis-compact-meta">
            {mode === 'online' ? `${model} · ${selectedMachine} · ${memoryDocs} memories` : activityLabel}
          </div>
        </div>
        <Waveform active={mode === 'listening' || mode === 'speaking'} />
        <div className="hidden xl:flex items-center gap-2">
          <StatusPill label="VOICE" ok={voiceAvailable} />
          <StatusPill label={wakeEnabled ? 'WAKE ON' : 'WAKE OFF'} ok={wakeEnabled} />
          <StatusPill label="COMMANDER" ok={Boolean(status?.execution.commander_connected)} />
          <StatusPill label="MEMORY" ok={Boolean(status?.memory.enabled)} />
        </div>
        <button className="jarvis-hud-button secondary" onClick={() => wakeSupported && setWakeEnabled((value) => !value)} disabled={!wakeSupported}>
          {wakeEnabled ? 'WAKE OFF' : 'WAKE ON'}
        </button>
        <button className="jarvis-hud-button" onClick={() => navigate('/dashboard')}>
          OPEN HUD
        </button>
      </section>
    );
  }

  return (
    <section
      ref={shellRef}
      className={`jarvis-hud-shell mode-${mode} ${ambient ? 'is-ambient' : ''}`}
      aria-label="Jarvis visual command core"
    >
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
          <StatusPill label="VOICE" ok={voiceAvailable} />
          <StatusPill label={wakeEnabled ? 'WAKE WORD ON' : 'WAKE WORD OFF'} ok={wakeEnabled} />
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
              <span className="jarvis-core-state">{shortLabels[mode]}</span>
            </div>
          </div>
          <Waveform active={mode === 'listening' || mode === 'speaking'} />
          <div className="jarvis-activity-caption">{activityLabel}</div>
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
          <span>{activityLabel}</span>
        </div>
        <div className="jarvis-actions">
          <button className="jarvis-hud-button secondary" onClick={() => navigate('/')}>CHAT</button>
          <button
            className="jarvis-hud-button secondary"
            onClick={() => wakeSupported && setWakeEnabled((value) => !value)}
            disabled={!wakeSupported}
            title={wakeSupported ? 'Enable continuous wake-word listening' : 'Wake word is not supported by this browser'}
          >
            {wakeEnabled ? 'WAKE WORD: ON' : 'WAKE WORD: OFF'}
          </button>
          <button className="jarvis-hud-button secondary" onClick={toggleFullscreen}>
            {ambient ? 'EXIT AMBIENT' : 'AMBIENT'}
          </button>
          <button className="jarvis-hud-button" onClick={() => navigate('/agents')}>AGENTS</button>
        </div>
      </div>
    </section>
  );
}
