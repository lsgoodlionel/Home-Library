import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from './client';
import { getCategoryStats } from './stats';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('category statistics normalization', () => {
  it('creates distinct stable keys and code-prefixed labels for duplicate names', async () => {
    vi.spyOn(apiClient, 'get')
      .mockResolvedValueOnce({
        data: [
          { id: 11, code: 'I247', name: '中国小说', count: 3 },
          { id: 12, code: 'I548', name: '中国小说', count: 2 },
          { id: null, code: null, name: '未分类', count: 1 },
        ],
      })
      .mockResolvedValueOnce({
        data: [
          { id: null, code: null, name: '未分类', count: 1 },
          { id: 11, code: 'I247', name: '中国小说', count: 3 },
        ],
      });

    const items = await getCategoryStats();
    const reorderedItems = await getCategoryStats();

    expect(items).toEqual([
      { id: 11, code: 'I247', name: 'I247 中国小说', count: 3, key: 'category:id:11' },
      { id: 12, code: 'I548', name: 'I548 中国小说', count: 2, key: 'category:id:12' },
      { id: undefined, code: undefined, name: '未分类', count: 1, key: 'category:uncategorized' },
    ]);
    expect(new Set(items.map((item) => item.key)).size).toBe(items.length);
    expect(reorderedItems[0].key).toBe('category:uncategorized');
  });
});
