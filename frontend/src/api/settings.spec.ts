import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchAIHealth, testAIConnection } from './ai';
import { API_TIMEOUTS, apiClient } from './client';
import { fetchAIModelSettings } from './settings';

const runtimePayload = {
  enabled: true,
  base_url: 'https://openclaw.lsgood.cn',
  default_model: 'qwen3.5:4b',
  connect_timeout_seconds: 20,
  read_timeout_seconds: 180,
  verify_tls: true,
  access_configured: true,
  uses_access: true,
  access_client_id: 'must-not-be-normalized',
  access_client_secret: 'must-not-be-normalized',
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AI settings API normalization', () => {
  it('normalizes sanitized runtime status without credential fields', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        active_provider: 'ollama',
        default_model: 'qwen3.5:4b',
        providers: [],
        ollama_runtime: runtimePayload,
      },
    });

    const settings = await fetchAIModelSettings();

    expect(settings.ollamaRuntime).toEqual({
      enabled: true,
      baseUrl: 'https://openclaw.lsgood.cn',
      defaultModel: 'qwen3.5:4b',
      connectTimeoutSeconds: 20,
      readTimeoutSeconds: 180,
      verifyTls: true,
      accessConfigured: true,
      usesAccess: true,
    });
    expect(JSON.stringify(settings)).not.toContain('must-not-be-normalized');
    expect(settings.ollamaRuntime).not.toHaveProperty('accessClientId');
    expect(settings.ollamaRuntime).not.toHaveProperty('accessClientSecret');
  });

  it('reads cached health by default and normalizes health fields', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        status: 'healthy',
        message: 'AI 服务连接正常',
        checked_at: '2026-10-20T08:00:00Z',
        version: '0.12.6',
        installed_model_count: 3,
        running_model_count: 1,
        generated: false,
        ollama_runtime: runtimePayload,
      },
    });

    const health = await fetchAIHealth();

    expect(get).toHaveBeenCalledWith('/ai/health', expect.objectContaining({ params: { refresh: false } }));
    expect(health.installedModelCount).toBe(3);
    expect(health.runningModelCount).toBe(1);
    expect(health.ollamaRuntime?.accessConfigured).toBe(true);
    expect(health.ollamaRuntime?.usesAccess).toBe(true);
    expect(JSON.stringify(health)).not.toContain('must-not-be-normalized');
  });

  it('separates active checks, ordinary tests, and explicit generation timeouts', async () => {
    expect(API_TIMEOUTS.aiHealth).toBe(240_000);
    expect(API_TIMEOUTS.aiGeneration).toBe(240_000);
    const payload = {
      status: 'healthy',
      message: 'AI 服务连接正常',
      checked_at: '2026-10-20T08:00:00Z',
      version: '0.12.6',
      installed_model_count: 3,
      running_model_count: 1,
      generated: false,
      ollama_runtime: runtimePayload,
    };
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: payload });
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: payload });

    await fetchAIHealth(true);
    await testAIConnection(false);
    await testAIConnection(true);

    expect(get).toHaveBeenCalledWith('/ai/health', {
      params: { refresh: true },
      timeout: API_TIMEOUTS.aiHealth,
    });
    expect(post).toHaveBeenNthCalledWith(
      1,
      '/ai/test-connection',
      { generate: false },
      { timeout: API_TIMEOUTS.aiHealth },
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/ai/test-connection',
      { generate: true },
      { timeout: API_TIMEOUTS.aiGeneration },
    );
  });
});
