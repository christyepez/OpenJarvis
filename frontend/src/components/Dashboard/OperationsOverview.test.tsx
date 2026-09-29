import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  AgentRoutingSummary,
  MemorySummary,
  ModelRoleSummary,
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
