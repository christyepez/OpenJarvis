import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MemorySummary, ModelRoleSummary } from './OperationsOverview';

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
