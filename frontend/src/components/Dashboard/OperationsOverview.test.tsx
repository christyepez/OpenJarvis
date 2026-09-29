import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  AgentRoutingSummary,
  MemorySummary,
  ModelRoleSummary,
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
            routed_model: 'qwen3.5:4b',
          },
          {
            id: 'a2',
            name: 'Code Reviewer',
            type: 'monitor_operative',
            status: 'idle',
            activity: '',
            capability: 'coding',
            routed_model: 'granite-code:3b',
          },
        ]}
      />,
    );

    expect(html).toContain('Visual QA');
    expect(html).toContain('multimodal');
    expect(html).toContain('qwen3.5:4b');
    expect(html).toContain('Code Reviewer');
    expect(html).toContain('coding');
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
