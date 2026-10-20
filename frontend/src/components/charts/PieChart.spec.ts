import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import PieChart from './PieChart.vue';

type PieChartItem = NonNullable<InstanceType<typeof PieChart>['$props']['items']>[number];
type KeyIsRequired = {} extends Pick<PieChartItem, 'key'> ? false : true;
const keyIsRequired: KeyIsRequired = true;

describe('PieChart', () => {
  it('uses caller-provided stable keys for duplicate display names', async () => {
    expect(keyIsRequired).toBe(true);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const wrapper = mount(PieChart, {
      props: {
        items: [
          { key: 'category:id:11', name: '中国小说', count: 3 },
          { key: 'category:id:12', name: '中国小说', count: 2 },
        ],
      },
    });

    expect(wrapper.findAll('.pie-chart__segment').map((node) => node.attributes('data-segment-key'))).toEqual([
      'category:id:11',
      'category:id:12',
    ]);

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
