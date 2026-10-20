import { afterEach, describe, expect, it, vi } from 'vitest';

import { detectDuplicate, summarizeBook } from './ai';
import { API_TIMEOUTS, apiClient } from './client';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AI business request contracts', () => {
  it('sends summarize input using backend raw_summary fields', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: { summary: '整理结果', model: 'qwen3:8b' },
    });

    await summarizeBook({
      title: '乡土中国',
      author: '费孝通',
      publisher: '三联书店',
      summary: '原始简介',
      model: 'qwen3:8b',
    });

    expect(post).toHaveBeenCalledWith(
      '/ai/summarize-book',
      {
        title: '乡土中国',
        author: '费孝通',
        publisher: '三联书店',
        raw_summary: '原始简介',
        model: 'qwen3:8b',
      },
      { timeout: API_TIMEOUTS.aiGeneration },
    );
  });

  it('sends duplicate candidates using backend first and second fields', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: { is_duplicate: true, confidence: 0.9, reason: '一致', model: 'qwen3:8b' },
    });
    const first = { title: '乡土中国', author: '费孝通' };
    const second = { title: '乡土中国', author: '费孝通' };

    await detectDuplicate({ bookA: first, bookB: second, model: 'qwen3:8b' });

    expect(post).toHaveBeenCalledWith(
      '/ai/detect-duplicate',
      { first, second, model: 'qwen3:8b' },
      { timeout: API_TIMEOUTS.aiGeneration },
    );
  });

  it('keeps frontend AI timeouts below the proxy budget', () => {
    expect(API_TIMEOUTS.aiHealth).toBe(240_000);
    expect(API_TIMEOUTS.aiGeneration).toBe(240_000);
  });
});
