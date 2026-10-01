import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  AgentRoutingSummary,
  MachineRoutingSummary,
  MemorySummary,
  ModelRoleSummary,
  ProjectBoardSummary,
  QualityRunSummary,
} from './OperationsOverview';

describe('OperationsOverview model role routing', () => {
  it('renders the selected local model for each capability', () => {
    const html = renderToStaticMarkup(
      <ModelRoleSummary
        roleModels={{
          general: 'qwen3.5:4b',
          coding: 'granite-code:3b',
          multimodal: 'qwen3.5:4b',
        }}
      />,
    );

    expect(html).toContain('general');
    expect(html).toContain('qwen3.5:4b');
    expect(html).toContain('coding');
    expect(html).toContain('granite-code:3b');
    expect(html).toContain('multimodal');
  });

  it('shows unassigned when no suitable model is available', () => {
    const html = renderToStaticMarkup(
      <ModelRoleSummary
        roleModels={{ general: null, coding: null, multimodal: null }}
      />,
    );

    expect(html.match(/unassigned/g)).toHaveLength(3);
  });
});

describe('OperationsOverview memory status', () => {
  it('renders the active backend and document count', () => {
    const html = renderToStaticMarkup(
      <MemorySummary
        memory={{ enabled: true, backend: 'sqlite', documents: 7 }}
      />,
    );

    expect(html).toContain('sqlite');
    expect(html).toContain('enabled');
    expect(html).toContain('7 stored documents');
  });

  it('renders disabled memory without inventing a document count', () => {
    const html = renderToStaticMarkup(
      <MemorySummary
        memory={{ enabled: false, backend: '', documents: null }}
      />,
    );

    expect(html).toContain('disabled');
    expect(html).toContain('Document count unavailable');
  });
});




describe('OperationsOverview machine routing', () => {
  it('renders selected fallback runtime capabilities', () => {
    const html = renderToStaticMarkup(
      <MachineRoutingSummary
        onProbe={() => undefined}
        execution={{ preferred_plane: 'commander', commander_connected: true }}
        machines={{
          selected: 'MarketingIndo',
          signal: 'runtime',
          primary: { name: 'trabajo', status: 'offline' },
          fallbacks: [
            {
              name: 'MarketingIndo',
              status: 'online',
              docker_available: true,
              gpu_available: true,
            },
          ],
        }}
      />,
    );

    expect(html).toContain('MarketingIndo');
    expect(html).toContain('selected');
    expect(html).toContain('runtime');
    expect(html).toContain('trabajo');
    expect(html).toContain('offline');
    expect(html).toContain('docker');
    expect(html).toContain('gpu');
    expect(html).toContain('commander:');
    expect(html).toContain('connected');
    expect(html).toContain('Refresh machines');
  });
});

describe('OperationsOverview agent routing', () => {
  it('renders capability and routed model for managed agents', () => {
    const html = renderToStaticMarkup(
      <AgentRoutingSummary
        onNextAction={() => undefined}
        agents={[
          {
            id: 'a1',
            name: 'Visual QA',
            type: 'orchestrator',
            status: 'idle',
            activity: '',
            capability: 'multimodal',
            model_policy: 'smart',
            routed_model: 'qwen3.5:4b',
            project_stream: 'frontend',
            domain: '',
            domain_task_key: '',
            domain_task_state: '',
            domain_next_action: '',
            domain_handoff_ready: false,
            domain_last_completed_at: 0,
            domain_quality_required: false,
            domain_quality_pipeline_id: '',
            domain_quality_status: 'not_required',
            domain_quality_stages: [],
            domain_result: '',
          },
          {
            id: 'a2',
            name: 'Code Reviewer',
            type: 'monitor_operative',
            status: 'idle',
            activity: '',
            capability: 'coding',
            model_policy: 'granite-code:3b',
            routed_model: 'granite-code:3b',
            project_stream: '',
            domain: 'professional',
            domain_task_key: 'task-professional-1',
            domain_task_state: 'quality_pending',
            domain_next_action: 'advance:task-professional-1',
            domain_handoff_ready: true,
            domain_last_completed_at: 1,
            domain_quality_required: true,
            domain_quality_pipeline_id: 'quality-domain-1',
            domain_quality_status: 'pending',
            domain_quality_stages: [
              {
                task_id: 'dq1',
                stage: 'anti-slop',
                kind: 'agent',
                status: 'completed',
                reviewer_agent_id: 'reviewer-a',
                template: 'anti_slop_reviewer',
                findings_count: 1,
              },
              {
                task_id: 'dq2',
                stage: 'thermos',
                kind: 'agent',
                status: 'pending',
                reviewer_agent_id: 'reviewer-b',
                template: 'thermos_reviewer',
                findings_count: 0,
              },
            ],
            domain_result: 'Code review complete and ready for follow-up.',
          },
        ]}
      />,
    );

    expect(html).toContain('Visual QA');
    expect(html).toContain('frontend · multimodal · smart');
    expect(html).toContain('qwen3.5:4b');
    expect(html).toContain('Code Reviewer');
    expect(html).toContain('professional · coding · granite-code:3b');
    expect(html).toContain('task: task-professional-1');
    expect(html).toContain('next: advance:task-professional-1');
    expect(html).toContain('Run next');
    expect(html).toContain('handoff ready');
    expect(html).toContain('task: quality_pending');
    expect(html).toContain('quality: pending');
    expect(html).toContain('anti-slop: completed');
    expect(html).toContain('thermos: pending');
    expect(html).toContain('Code review complete and ready for follow-up.');
    expect(html).toContain('granite-code:3b');
  });
});


describe('OperationsOverview quality runs', () => {
  it('renders persisted pipeline status and stages', () => {
    const html = renderToStaticMarkup(
      <QualityRunSummary
        quality={{
          total: 1,
          by_status: { active: 1 },
          pipelines: [
            {
              pipeline_id: 'abc123',
              coordinator_agent_id: 'quality-abc123',
              objective: 'Validate dashboard release',
              status: 'active',
              stages: [
                {
                  task_id: 't1',
                  stage: 'build-tests',
                  kind: 'gate',
                  status: 'completed',
                  reviewer_agent_id: '',
                  template: '',
                  findings_count: 0,
                },
                {
                  task_id: 't2',
                  stage: 'anti-slop',
                  kind: 'agent',
                  status: 'active',
                  reviewer_agent_id: 'reviewer-1',
                  template: 'anti_slop_reviewer',
                  findings_count: 1,
                },
              ],
            },
          ],
        }}
      />,
    );

    expect(html).toContain('Validate dashboard release');
    expect(html).toContain('active');
    expect(html).toContain('build-tests: completed');
    expect(html).toContain('anti-slop: active');
  });

  it('renders an empty state when there are no quality runs', () => {
    const html = renderToStaticMarkup(
      <QualityRunSummary
        quality={{ total: 0, by_status: {}, pipelines: [] }}
      />,
    );

    expect(html).toContain('No quality runs');
  });
});


describe('OperationsOverview project execution boards', () => {
  it('renders project status, waves, streams and runtime machines', () => {
    const html = renderToStaticMarkup(
      <ProjectBoardSummary
        onNextAction={() => undefined}
        projects={{
          total: 1,
          by_status: { pending: 1 },
          projects: [
            {
              project_key: 'portal|repo',
              name: 'Portal',
              repository: 'https://github.com/example/portal',
              orchestrator_agent_id: 'project-1',
              runtime_machines: ['trabajo', 'MarketingIndo'],
              status: 'pending',
              next_action: 'dispatch:architecture',
              ready_streams: ['architecture'],
              active_streams: ['backend'],
              handoff_ready_streams: ['backend'],
              blocked_streams: ['integration'],
              done_streams: [],
              quality_pipeline_id: 'quality-1',
              quality_status: 'pending',
              quality_stages: [
                {
                  task_id: 'q1',
                  stage: 'build-tests',
                  kind: 'gate',
                  status: 'pending',
                  reviewer_agent_id: '',
                  template: '',
                  findings_count: 0,
                },
                {
                  task_id: 'q2',
                  stage: 'anti-slop',
                  kind: 'agent',
                  status: 'pending',
                  reviewer_agent_id: 'reviewer-1',
                  template: 'anti_slop_reviewer',
                  findings_count: 0,
                },
              ],
              streams: [
                {
                  task_id: 'a1',
                  stream: 'architecture',
                  wave: 'A',
                  execution_state: 'READY',
                  order: 0,
                  status: 'pending',
                  worker_agent_id: '',
                  worker_status: '',
                  handoff_ready: false,
                  findings_count: 0,
                  branch: '',
                  workspace: '',
                  runtime_machine: 'trabajo',
                  runtime_machine_status: 'unavailable',
                  depends_on_task_ids: [],
                },
                {
                  task_id: 'b1',
                  stream: 'backend',
                  wave: 'B',
                  execution_state: 'PARALLEL',
                  order: 1,
                  status: 'active',
                  worker_agent_id: 'project-backend-1',
                  worker_status: 'completed_tick',
                  handoff_ready: true,
                  findings_count: 1,
                  branch: 'openjarvis/portal/backend',
                  workspace: 'C:/worktrees/portal/backend',
                  runtime_machine: 'MarketingIndo',
                  runtime_machine_status: 'online',
                  depends_on_task_ids: ['a1'],
                },
              ],
            },
          ],
        }}
      />,
    );

    expect(html).toContain('Portal');
    expect(html).toContain('https://github.com/example/portal');
    expect(html).toContain('READY: 1');
    expect(html).toContain('ACTIVE: 1');
    expect(html).toContain('REVIEW: 1');
    expect(html).toContain('BLOCKED: 1');
    expect(html).toContain('next: dispatch:architecture');
    expect(html).toContain('runtime: unavailable');
    expect(html).toContain('runtime: online');
    expect(html).toContain('Run next');
    expect(html).toContain('build-tests: pending');
    expect(html).toContain('anti-slop: pending');
    expect(html).toContain('quality: pending');
    expect(html).toContain('A.architecture: pending');
    expect(html).toContain('B.backend: active');
    expect(html).toContain('openjarvis/portal/backend');
    expect(html).toContain('machine: MarketingIndo');
    expect(html).toContain('handoff ready: 1');
    expect(html).toContain('completed_tick');
    expect(html).toContain('worker: project-backend-1');
    expect(html).toContain('runtime: trabajo, MarketingIndo');
  });

  it('renders an empty project state', () => {
    const html = renderToStaticMarkup(
      <ProjectBoardSummary
        projects={{ total: 0, by_status: {}, projects: [] }}
      />,
    );

    expect(html).toContain('No bootstrapped projects');
  });
});
