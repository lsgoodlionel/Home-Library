import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  detectDuplicate,
  fetchAIHealth,
  fetchAIProviderModels,
  generateAIProviderTest,
  summarizeBook,
  testAIProvider,
} from './ai';
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

describe('provider-aware AI diagnostics', () => {
  const providerResponse = {
    provider: 'openai',
    status: 'available',
    message: '连接正常',
    checked_at: '2026-10-21T00:00:00Z',
    effective_model: 'gpt-5-mini',
    safe_base_url: 'https://api.openai.com/v1',
    credential_state: 'configured',
    models: [{ provider: 'openai', id: 'gpt-5-mini', name: 'GPT-5 mini' }],
    details: { region: 'global' },
  };

  it('normalizes the account health response independently from server Ollama health', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: providerResponse });

    const health = await fetchAIHealth(true);

    expect(get).toHaveBeenCalledWith('/ai/health', {
      params: { refresh: true },
      timeout: API_TIMEOUTS.aiHealth,
    });
    expect(health).toEqual({
      provider: 'openai',
      status: 'available',
      message: '连接正常',
      checkedAt: '2026-10-21T00:00:00Z',
      effectiveModel: 'gpt-5-mini',
      safeBaseUrl: 'https://api.openai.com/v1',
      credentialState: 'configured',
      models: [{ provider: 'openai', id: 'gpt-5-mini', name: 'GPT-5 mini' }],
      details: { region: 'global' },
    });
    expect(health).not.toHaveProperty('ollamaRuntime');
  });

  it.each([
    ['testAIProvider', testAIProvider, '/ai/providers/openai/test', API_TIMEOUTS.aiHealth],
    ['fetchAIProviderModels', fetchAIProviderModels, '/ai/providers/openai/models', API_TIMEOUTS.aiHealth],
    ['generateAIProviderTest', generateAIProviderTest, '/ai/providers/openai/generate-test', API_TIMEOUTS.aiGeneration],
  ] as const)('%s sends an unsaved draft only in the request body', async (_name, operation, path, timeout) => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: providerResponse });
    const draft = {
      provider: 'openai' as const,
      baseUrl: 'https://draft.example.test/v1',
      model: 'draft-model',
      apiKey: 'draft-key-sensitive-marker',
    };

    const result = await operation('openai', draft);

    expect(post).toHaveBeenCalledWith(path, {
      provider: 'openai',
      base_url: 'https://draft.example.test/v1',
      model: 'draft-model',
      api_key: 'draft-key-sensitive-marker',
    }, { timeout });
    expect(result.credentialState).toBe('configured');
    expect(JSON.stringify(result)).not.toContain('draft-key-sensitive-marker');
  });

  it('omits an empty draft key instead of changing credential semantics', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: providerResponse });

    await testAIProvider('openai', {
      provider: 'openai',
      baseUrl: 'https://api.openai.com/v1',
      model: 'gpt-5-mini',
      apiKey: '',
    });

    expect(post.mock.calls[0][1]).not.toHaveProperty('api_key');
  });

  it('keeps model responses provider-scoped', async () => {
    const post = vi.spyOn(apiClient, 'post')
      .mockResolvedValueOnce({ data: providerResponse })
      .mockResolvedValueOnce({
        data: {
          ...providerResponse,
          provider: 'gemini',
          effective_model: 'gemini-2.5-flash',
          models: [{ provider: 'gemini', id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' }],
        },
      });

    const openai = await fetchAIProviderModels('openai');
    const gemini = await fetchAIProviderModels('gemini');

    expect(openai.models).toEqual([{ provider: 'openai', id: 'gpt-5-mini', name: 'GPT-5 mini' }]);
    expect(gemini.models).toEqual([{
      provider: 'gemini', id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash',
    }]);
  });
});
