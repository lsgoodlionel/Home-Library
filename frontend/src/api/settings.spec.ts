import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchAIHealth, testAIConnection } from './ai';
import { API_TIMEOUTS, apiClient } from './client';
import {
  fetchAIModelSettings,
  fetchSystemAIModels,
  fetchSystemAIConfig,
  resetSystemAIConfig,
  saveAIModelSettings,
  saveSystemAIConfig,
  testSystemAIConfig,
} from './settings';

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
  it.each([
    ['configured', true],
    ['missing', false],
    ['unusable', false],
  ] as const)('normalizes %s credential state and saved-key compatibility', async (credentialState, hasApiKey) => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        ai_enabled: true,
        active_provider: 'openai',
        default_model: 'gpt-5-mini',
        providers: [{
          provider: 'openai',
          enabled: true,
          base_url: 'https://api.openai.com/v1',
          default_model: 'gpt-5-mini',
          note: '',
          credential_state: credentialState,
          has_api_key: hasApiKey,
        }],
        ollama_runtime: runtimePayload,
      },
    });

    const loaded = await fetchAIModelSettings();

    expect(loaded.providers[0]).toMatchObject({ credentialState, hasApiKey });
  });

  it('normalizes AI disabled and provider credential states', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        ai_enabled: false,
        active_provider: 'openai',
        default_model: 'gpt-5-mini',
        providers: [{
          provider: 'openai',
          enabled: true,
          base_url: 'https://api.openai.com/v1',
          default_model: 'gpt-5-mini',
          note: '',
          credential_state: 'unusable',
          has_api_key: false,
        }],
        ollama_runtime: runtimePayload,
      },
    });

    const settings = await fetchAIModelSettings();

    expect(settings.aiEnabled).toBe(false);
    expect(settings.providers[0].credentialState).toBe('unusable');
    expect(settings.providers[0]).not.toHaveProperty('apiKey');
  });

  it.each([
    ['preserves a saved key when draft is empty', '', false, false],
    ['replaces a saved key when a draft is present', 'replacement-key', false, true],
    ['clears a saved key only with the explicit flag', '', true, false],
  ])('%s', async (_label, apiKey, clearApiKey, includesKey) => {
    const put = vi.spyOn(apiClient, 'put').mockResolvedValue({
      data: {
        ai_enabled: true,
        active_provider: 'openai',
        default_model: 'gpt-5-mini',
        providers: [],
        ollama_runtime: runtimePayload,
      },
    });

    await saveAIModelSettings({
      aiEnabled: true,
      activeProvider: 'openai',
      defaultModel: 'gpt-5-mini',
      providers: [{
        provider: 'openai',
        enabled: true,
        baseUrl: 'https://api.openai.com/v1',
        defaultModel: 'gpt-5-mini',
        note: '',
        hasApiKey: true,
        credentialState: 'configured',
        apiKey,
        clearApiKey,
      }],
      ollamaRuntime: {
        enabled: true,
        baseUrl: runtimePayload.base_url,
        defaultModel: runtimePayload.default_model,
        connectTimeoutSeconds: 20,
        readTimeoutSeconds: 180,
        verifyTls: true,
        accessConfigured: true,
        usesAccess: true,
      },
    });

    const body = put.mock.calls[0][1] as { providers: Array<Record<string, unknown>> };
    expect(body).toMatchObject({ ai_enabled: true });
    expect(body.providers[0].clear_api_key).toBe(clearApiKey);
    expect(body.providers[0].hasOwnProperty('api_key')).toBe(includesKey);
  });

  it('loads server models from the server-only endpoint', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: { models: [{ name: 'qwen3.5:4b', size: '3.2 GB', modified_at: '2026-10-21T00:00:00Z' }] },
    });

    const models = await fetchSystemAIModels();

    expect(get).toHaveBeenCalledWith('/system/ai-config/models', {
      timeout: API_TIMEOUTS.aiHealth,
    });
    expect(models).toEqual([{
      name: 'qwen3.5:4b',
      size: '3.2 GB',
      modifiedAt: '2026-10-21T00:00:00Z',
    }]);
  });

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
        provider: 'ollama',
        status: 'available',
        message: 'AI 服务连接正常',
        checked_at: '2026-10-20T08:00:00Z',
        effective_model: 'qwen3.5:4b',
        safe_base_url: 'https://openclaw.lsgood.cn',
        credential_state: 'configured',
        models: [],
        details: {
          version: '0.12.6',
          installed_model_count: 3,
          running_model_count: 1,
          uses_access: true,
        },
      },
    });

    const health = await fetchAIHealth();

    expect(get).toHaveBeenCalledWith('/ai/health', expect.objectContaining({ params: { refresh: false } }));
    expect(health.details?.installedModelCount).toBe(3);
    expect(health.details?.runningModelCount).toBe(1);
    expect(health.details?.usesAccess).toBe(true);
    expect(health).not.toHaveProperty('ollamaRuntime');
    expect(JSON.stringify(health)).not.toContain('must-not-be-normalized');
  });

  it('separates active checks, ordinary tests, and explicit generation timeouts', async () => {
    expect(API_TIMEOUTS.aiHealth).toBe(240_000);
    expect(API_TIMEOUTS.aiGeneration).toBe(240_000);
    const ollamaPayload = {
      status: 'healthy',
      message: 'AI 服务连接正常',
      checked_at: '2026-10-20T08:00:00Z',
      version: '0.12.6',
      installed_model_count: 3,
      running_model_count: 1,
      generated: false,
      ollama_runtime: runtimePayload,
    };
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        provider: 'ollama',
        status: 'available',
        message: 'AI 服务连接正常',
        checked_at: '2026-10-20T08:00:00Z',
        effective_model: 'qwen3.5:4b',
        safe_base_url: 'https://openclaw.lsgood.cn',
        credential_state: 'configured',
        models: [],
        details: {},
      },
    });
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: ollamaPayload });

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

const systemConfigPayload = {
  enabled: true,
  default_base_url: 'https://ollama.example.test',
  trusted_base_url: 'https://ollama.example.test',
  default_model: 'qwen3.5:4b',
  connect_timeout_seconds: 20,
  read_timeout_seconds: 180,
  verify_tls: true,
  credential_state: {
    access_client_id_configured: true,
    access_client_secret_configured: true,
    credentials_usable: true,
    source: 'environment',
    access_client_id: 'saved-client-must-not-leak',
    access_client_secret: 'saved-secret-must-not-leak',
  },
  configuration_source: 'environment',
  config_version: 7,
  admin_password: 'admin-password-must-not-leak',
  upgrade_password: 'upgrade-password-must-not-leak',
};

describe('system AI settings API adapters', () => {
  it('maps snake_case and omits every persisted credential value', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: systemConfigPayload });

    const config = await fetchSystemAIConfig();

    expect(config).toEqual({
      enabled: true,
      defaultBaseUrl: 'https://ollama.example.test',
      trustedBaseUrl: 'https://ollama.example.test',
      defaultModel: 'qwen3.5:4b',
      connectTimeoutSeconds: 20,
      readTimeoutSeconds: 180,
      verifyTls: true,
      credentialState: {
        accessClientIdConfigured: true,
        accessClientSecretConfigured: true,
        credentialsUsable: true,
        source: 'environment',
      },
      configurationSource: 'environment',
      configVersion: 7,
    });
    expect(JSON.stringify(config)).not.toContain('must-not-leak');
    expect(config.credentialState).not.toHaveProperty('accessClientId');
    expect(config.credentialState).not.toHaveProperty('accessClientSecret');
  });

  it.each([
    {
      label: 'preserves credentials when both submitted values are blank',
      credentials: { accessClientId: '', accessClientSecret: '', clearAccessCredentials: false },
      expected: { clear_access_credentials: false },
    },
    {
      label: 'replaces credentials only with a complete pair',
      credentials: {
        accessClientId: 'replacement-client',
        accessClientSecret: 'replacement-secret',
        clearAccessCredentials: false,
      },
      expected: {
        access_client_id: 'replacement-client',
        access_client_secret: 'replacement-secret',
        clear_access_credentials: false,
      },
    },
    {
      label: 'clears credentials only when explicitly selected',
      credentials: { accessClientId: '', accessClientSecret: '', clearAccessCredentials: true },
      expected: { clear_access_credentials: true },
    },
  ])('$label', async ({ credentials, expected }) => {
    const put = vi.spyOn(apiClient, 'put').mockResolvedValue({ data: systemConfigPayload });

    await saveSystemAIConfig({
      enabled: true,
      defaultBaseUrl: 'https://ollama.example.test',
      trustedBaseUrl: 'https://ollama.example.test',
      defaultModel: 'qwen3.5:4b',
      connectTimeoutSeconds: 20,
      readTimeoutSeconds: 180,
      verifyTls: true,
      confirmInsecureTls: false,
      adminPassword: 'current-admin-password',
      upgradePassword: 'server-upgrade-password',
      ...credentials,
    });

    expect(put).toHaveBeenCalledWith('/system/ai-config', expect.objectContaining({
      enabled: true,
      default_base_url: 'https://ollama.example.test',
      trusted_base_url: 'https://ollama.example.test',
      default_model: 'qwen3.5:4b',
      connect_timeout_seconds: 20,
      read_timeout_seconds: 180,
      verify_tls: true,
      confirm_insecure_tls: false,
      admin_password: 'current-admin-password',
      upgrade_password: 'server-upgrade-password',
      ...expected,
    }));
    const body = put.mock.calls[0][1] as Record<string, unknown>;
    if (!expected.access_client_id) {
      expect(body).not.toHaveProperty('access_client_id');
      expect(body).not.toHaveProperty('access_client_secret');
    }
  });

  it('sends reset authentication in the DELETE body with explicit confirmation', async () => {
    const deleteRequest = vi.spyOn(apiClient, 'delete').mockResolvedValue({ data: systemConfigPayload });

    await resetSystemAIConfig({
      adminPassword: 'current-admin-password',
      upgradePassword: 'server-upgrade-password',
    });

    expect(deleteRequest).toHaveBeenCalledWith('/system/ai-config', {
      data: {
        admin_password: 'current-admin-password',
        upgrade_password: 'server-upgrade-password',
        confirm_reset: true,
      },
    });
  });

  it('does not silently convert a partial credential replacement into preserve', async () => {
    const put = vi.spyOn(apiClient, 'put').mockResolvedValue({ data: systemConfigPayload });

    await saveSystemAIConfig({
      enabled: true,
      defaultBaseUrl: 'https://ollama.example.test',
      trustedBaseUrl: 'https://ollama.example.test',
      defaultModel: 'qwen3.5:4b',
      connectTimeoutSeconds: 20,
      readTimeoutSeconds: 180,
      verifyTls: true,
      confirmInsecureTls: false,
      adminPassword: 'current-admin-password',
      upgradePassword: 'server-upgrade-password',
      accessClientId: 'partial-client',
      clearAccessCredentials: false,
    });

    expect(put).toHaveBeenCalledWith('/system/ai-config', expect.objectContaining({
      access_client_id: 'partial-client',
    }));
    expect(put.mock.calls[0][1]).not.toHaveProperty('access_client_secret');
  });

  it('normalizes the persisted-config test result without secret fields', async () => {
    vi.spyOn(apiClient, 'post').mockResolvedValue({
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

    const health = await testSystemAIConfig();

    expect(health).toEqual(expect.objectContaining({
      status: 'healthy',
      checkedAt: '2026-10-20T08:00:00Z',
      installedModelCount: 3,
      runningModelCount: 1,
    }));
    expect(JSON.stringify(health)).not.toContain('must-not-be-normalized');
  });
});
