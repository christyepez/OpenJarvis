import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  AgentRoutingSummary,
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


describe('OperationsOverview agent routing', () => {
  it('renders capability and routed model for managed agents', () => {
    const html = renderToStaticMarkup(
      <AgentRoutingSummary
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
            project_stream: 'backend',
          },
        ]}
      />,
    );

    expect(html).toContain('Visual QA');
    expect(html).toContain('frontend · multimodal · smart');
    expect(html).toContain('qwen3.5:4b');
    expect(html).toContain('Code Reviewer');
    expect(html).toContain('backend · coding · granite-code:3b');
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
              streams: [
                {
                  task_id: 'a1',
                  stream: 'architecture',
                  wave: 'A',
                  execution_state: 'READY',
                  order: 0,
                  status: 'pending',
                  worker_agent_id: '',
                  branch: '',
                  workspace: '',
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
                  branch: 'openjarvis/portal/backend',
                  workspace: 'C:/worktrees/portal/backend',
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
    expect(html).toContain('A.architecture: pending');
    expect(html).toContain('B.backend: active');
    expect(html).toContain('openjarvis/portal/backend');
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
