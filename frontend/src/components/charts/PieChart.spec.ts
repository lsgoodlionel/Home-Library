import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import PieChart from './PieChart.vue';

describe('PieChart', () => {
  it('uses caller-provided stable keys for duplicate display names', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const wrapper = mount(PieChart, {
      props: {
        items: [
          { key: 'category:id:11', name: '中国小说', count: 3 },
          { key: 'category:id:12', name: '中国小说', count: 2 },
        ],
      },
    });

    await wrapper.setProps({
      items: [
        { key: 'category:id:12', name: '中国小说', count: 4 },
        { key: 'category:id:11', name: '中国小说', count: 1 },
      ],
    });

    expect(wrapper.findAll('.pie-chart__segment').map((node) => node.attributes('data-segment-key'))).toEqual([
      'category:id:12',
      'category:id:11',
    ]);
    expect(wrapper.findAll('.pie-chart__legend-item').map((node) => node.attributes('data-segment-key'))).toEqual([
      'category:id:12',
      'category:id:11',
    ]);
    expect(warn.mock.calls.flat().join(' ')).not.toContain('Duplicate keys');
    warn.mockRestore();
  });
});
