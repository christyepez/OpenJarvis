import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ModelRoleSummary } from './OperationsOverview';

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
