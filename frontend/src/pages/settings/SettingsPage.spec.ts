import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AIProviderHealthStatus, OllamaHealthStatus } from '@/types/ai';
import ServerAISettingsPanel from '@/components/ai/ServerAISettingsPanel.vue';
import type { AIModelSettings, OllamaRuntimeStatus, SystemAIConfig } from '@/types/settings';
import SettingsPage from './SettingsPage.vue';

const authState = vi.hoisted(() => ({ isAdmin: true }));
const mocks = vi.hoisted(() => ({
  fetchAIHealth: vi.fn(),
  testAIConnection: vi.fn(),
  fetchAvailableModels: vi.fn(),
  fetchAIModelSettings: vi.fn(),
  saveAIModelSettings: vi.fn(),
  fetchExternalSearchSettings: vi.fn(),
  saveExternalSearchSettings: vi.fn(),
  saveLocalSettings: vi.fn(),
  fetchAppVersion: vi.fn(),
  fetchSystemAIConfig: vi.fn(),
  resetSystemAIConfig: vi.fn(),
  saveSystemAIConfig: vi.fn(),
  testSystemAIConfig: vi.fn(),
}));

vi.mock('@/api/ai', () => ({
  classifyBook: vi.fn(),
  fetchAIHealth: mocks.fetchAIHealth,
  testAIConnection: mocks.testAIConnection,
}));

vi.mock('@/api/settings', () => ({
  DEFAULT_EXTERNAL_PROVIDER_ORDER: ['nlc', 'isbn_work', 'douban', 'google_books', 'open_library'],
  EXTERNAL_BOOK_PROVIDERS: [
    { key: 'nlc', name: 'NLC', description: '' },
    { key: 'isbn_work', name: 'ISBN Work', description: '' },
    { key: 'douban', name: '豆瓣', description: '' },
    { key: 'google_books', name: 'Google Books', description: '' },
    { key: 'open_library', name: 'Open Library', description: '' },
  ],
  fetchAppVersion: mocks.fetchAppVersion,
  fetchExternalSearchSettings: mocks.fetchExternalSearchSettings,
  fetchAIModelSettings: mocks.fetchAIModelSettings,
  fetchAvailableModels: mocks.fetchAvailableModels,
  fetchSystemAIConfig: mocks.fetchSystemAIConfig,
  loadLocalSettings: vi.fn(() => ({
    ollamaBaseUrl: 'http://localhost:11434',
    defaultModel: '',
    externalSearchEnabled: true,
    externalProviderOrder: ['nlc', 'isbn_work', 'douban', 'google_books', 'open_library'],
  })),
  saveAIModelSettings: mocks.saveAIModelSettings,
  saveExternalSearchSettings: mocks.saveExternalSearchSettings,
  saveLocalSettings: mocks.saveLocalSettings,
  resetSystemAIConfig: mocks.resetSystemAIConfig,
  saveSystemAIConfig: mocks.saveSystemAIConfig,
  testSystemAIConfig: mocks.testSystemAIConfig,
  validateExternalProvider: vi.fn(),
}));

vi.mock('@/api/books', () => ({
  bookDetailToForm: vi.fn(),
  getBook: vi.fn(),
  getBooks: vi.fn(),
  getCategoryOptions: vi.fn(),
  updateBook: vi.fn(),
}));

vi.mock('@/api/importExport', () => ({
  confirmBooksImport: vi.fn(),
  downloadBooksExport: vi.fn(),
  downloadImportTemplate: vi.fn(),
  previewBooksImport: vi.fn(),
}));

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => authState,
}));

const currentRuntime: OllamaRuntimeStatus = {
  enabled: true,
  baseUrl: 'https://current.example.com',
  defaultModel: 'selected-model',
  connectTimeoutSeconds: 20,
  readTimeoutSeconds: 180,
  verifyTls: true,
  accessConfigured: true,
  usesAccess: true,
};

const staleRuntime: OllamaRuntimeStatus = {
  ...currentRuntime,
  baseUrl: 'https://other-account.example.com',
  defaultModel: 'other-model',
};

const systemConfig: SystemAIConfig = {
  enabled: true,
  defaultBaseUrl: currentRuntime.baseUrl,
  trustedBaseUrl: currentRuntime.baseUrl,
  defaultModel: currentRuntime.defaultModel,
  connectTimeoutSeconds: currentRuntime.connectTimeoutSeconds,
  readTimeoutSeconds: currentRuntime.readTimeoutSeconds,
  verifyTls: currentRuntime.verifyTls,
  credentialState: {
    accessClientIdConfigured: true,
    accessClientSecretConfigured: true,
    credentialsUsable: true,
    source: 'database',
  },
  configurationSource: 'database',
  configVersion: 2,
};

function settings(runtime = currentRuntime): AIModelSettings {
  return {
    aiEnabled: true,
    activeProvider: 'ollama',
    defaultModel: runtime.defaultModel,
    providers: [{
      provider: 'ollama',
      enabled: true,
      baseUrl: runtime.baseUrl,
      apiKey: '',
      defaultModel: runtime.defaultModel,
      note: 'Ollama',
      hasApiKey: false,
      credentialState: 'configured',
    }],
    ollamaRuntime: runtime,
  };
}

function disabledSettings(): AIModelSettings {
  return { ...settings(), aiEnabled: false };
}

function health(
  status: OllamaHealthStatus['status'] = 'healthy',
  runtime = currentRuntime,
): OllamaHealthStatus {
  return {
    status,
    message: status === 'error' ? '连接 AI 服务超时' : 'AI 服务连接正常',
    checkedAt: '2026-10-20T08:00:00Z',
    version: status === 'healthy' ? '0.12.6' : null,
    installedModelCount: status === 'healthy' ? 3 : 0,
    runningModelCount: status === 'healthy' ? 1 : 0,
    generated: false,
    ollamaRuntime: runtime,
  };
}

function providerHealth(
  status: AIProviderHealthStatus['status'] = 'available',
  runtime = currentRuntime,
): AIProviderHealthStatus {
  return {
    provider: 'ollama',
    status,
    message: status === 'unavailable' ? '连接 AI 服务超时' : status === 'unchecked' ? '尚未检查' : 'AI 服务连接正常',
    checkedAt: '2026-10-20T08:00:00Z',
    effectiveModel: runtime.defaultModel,
    safeBaseUrl: runtime.baseUrl,
    credentialState: 'configured',
    models: [],
    details: {
      version: status === 'available' ? '0.12.6' : undefined,
      installedModelCount: status === 'available' ? 3 : 0,
      runningModelCount: status === 'available' ? 1 : 0,
      usesAccess: runtime.usesAccess,
    },
  };
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function mountPage(): Promise<VueWrapper> {
  const wrapper = mount(SettingsPage, { global: { plugins: [ElementPlus] } });
  await flushPromises();
  return wrapper;
}

function button(wrapper: VueWrapper, text: string) {
  const found = wrapper.findAll('button').find((item) => item.text().includes(text));
  if (!found) throw new Error(`未找到按钮：${text}`);
  return found;
}

beforeEach(() => {
  vi.clearAllMocks();
  authState.isAdmin = true;
  mocks.fetchAppVersion.mockResolvedValue({ appName: 'Home Library', version: 'test', environment: 'test' });
  mocks.fetchExternalSearchSettings.mockResolvedValue({ providers: [] });
  mocks.saveExternalSearchSettings.mockResolvedValue({ providers: [] });
  mocks.fetchAIModelSettings.mockResolvedValue(settings());
  mocks.saveAIModelSettings.mockResolvedValue(settings());
  mocks.fetchAIHealth.mockResolvedValue(providerHealth());
  mocks.testAIConnection.mockResolvedValue(health());
  mocks.fetchAvailableModels.mockResolvedValue([{ name: 'first-model' }]);
  mocks.fetchSystemAIConfig.mockResolvedValue(systemConfig);
  mocks.resetSystemAIConfig.mockResolvedValue(systemConfig);
  mocks.saveSystemAIConfig.mockResolvedValue(systemConfig);
  mocks.testSystemAIConfig.mockResolvedValue(health());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('SettingsPage AI status orchestration', () => {
  it('keeps a loaded AI-off account disabled when saving unrelated settings', async () => {
    mocks.fetchAIModelSettings.mockResolvedValueOnce(disabledSettings());
    mocks.saveAIModelSettings.mockResolvedValueOnce(disabledSettings());

    const wrapper = await mountPage();
    expect(mocks.fetchAIHealth).not.toHaveBeenCalled();
    expect(mocks.fetchAvailableModels).not.toHaveBeenCalled();

    await button(wrapper, '保存设置').trigger('click');
    await flushPromises();

    expect(mocks.saveAIModelSettings).toHaveBeenCalledWith(expect.objectContaining({ aiEnabled: false }));
    expect(mocks.fetchAIHealth).not.toHaveBeenCalled();
    expect(mocks.fetchAvailableModels).not.toHaveBeenCalled();
  });

  it.each([
    ['configured', true],
    ['missing', false],
    ['unusable', false],
  ] as const)('renders the loaded %s credential state without losing the saved-key hint', async (credentialState, hasApiKey) => {
    const loaded = settings();
    loaded.activeProvider = 'openai';
    loaded.defaultModel = 'gpt-5-mini';
    loaded.providers = [{
      provider: 'openai',
      enabled: true,
      baseUrl: 'https://api.openai.com/v1',
      apiKey: '',
      defaultModel: 'gpt-5-mini',
      note: '',
      credentialState,
      hasApiKey,
    }];
    mocks.fetchAIModelSettings.mockResolvedValueOnce(loaded);

    const wrapper = await mountPage();

    const hint = '当前账号已有已保存 Key；输入新值会覆盖。';
    expect(wrapper.text().includes(hint)).toBe(credentialState === 'configured');
  });

  it('separates_server_settings_runtime_status_and_account_preferences', async () => {
    const wrapper = await mountPage();
    const text = wrapper.text();
    const serverIndex = text.indexOf('服务器 AI 配置');
    const runtimeIndex = text.indexOf('当前运行状态');
    const accountIndex = text.indexOf('当前账号 AI 偏好');

    expect(serverIndex).toBeGreaterThan(-1);
    expect(runtimeIndex).toBeGreaterThan(serverIndex);
    expect(accountIndex).toBeGreaterThan(runtimeIndex);
    expect(wrapper.find('.ai-settings-sections .el-card').exists()).toBe(false);
    expect(wrapper.findAllComponents(ServerAISettingsPanel)).toHaveLength(1);
  });

  it('reloads_account_runtime_and_clears_stale_health_after_server_change', async () => {
    const pendingSettings = deferred<AIModelSettings>();
    const nextRuntime = { ...currentRuntime, baseUrl: 'https://reloaded.example.com' };
    const callOrder: string[] = [];
    mocks.fetchAIModelSettings.mockImplementationOnce(async () => settings());
    mocks.fetchAIModelSettings.mockImplementationOnce(() => {
      callOrder.push('settings');
      return pendingSettings.promise;
    });
    mocks.fetchAIHealth.mockImplementation(async (refresh: boolean) => {
      callOrder.push(`health:${refresh}`);
      return providerHealth('available', refresh ? nextRuntime : currentRuntime);
    });
    const wrapper = await mountPage();
    callOrder.length = 0;

    wrapper.findComponent(ServerAISettingsPanel).vm.$emit('runtime-changed', systemConfig);
    await flushPromises();

    expect(callOrder).toEqual(['settings']);
    expect(wrapper.text()).toContain('正在同步运行配置，尚未检查连接');
    expect(wrapper.find('.ollama-status').exists()).toBe(false);

    pendingSettings.resolve(settings(nextRuntime));
    await flushPromises();

    expect(callOrder).toEqual(['settings', 'health:true']);
    expect(mocks.fetchAIHealth).toHaveBeenLastCalledWith(true);
    expect(wrapper.text()).toContain(nextRuntime.baseUrl);
  });

  it('invalidates_stale_runtime_when_saved_server_settings_cannot_reload_and_allows_sync_retry', async () => {
    const success = vi.spyOn(ElMessage, 'success');
    const error = vi.spyOn(ElMessage, 'error');
    const nextRuntime = { ...currentRuntime, baseUrl: 'https://new-server.example.com', defaultModel: 'new-server-model' };
    const wrapper = await mountPage();
    const runtimeSection = () => wrapper.get('section[aria-labelledby="runtime-status-heading"]');
    expect(runtimeSection().text()).toContain('连接正常');
    expect(runtimeSection().text()).toContain(currentRuntime.baseUrl);
    mocks.fetchAIModelSettings.mockRejectedValueOnce(new Error('account runtime reload unavailable'));
    mocks.saveSystemAIConfig.mockResolvedValueOnce({ ...systemConfig, defaultBaseUrl: nextRuntime.baseUrl, defaultModel: nextRuntime.defaultModel });

    await button(wrapper, '保存服务器配置').trigger('click');
    await flushPromises();
    await wrapper.get('input[data-testid="admin-password"]').setValue('synthetic-admin-password');
    await wrapper.get('input[data-testid="upgrade-password"]').setValue('synthetic-upgrade-password');
    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();

    expect(success).toHaveBeenCalledWith('服务器 AI 配置已保存');
    expect(runtimeSection().text()).toContain('运行配置未同步，尚未检查连接');
    expect(runtimeSection().find('.ollama-status').exists()).toBe(false);
    expect(runtimeSection().text()).not.toContain(currentRuntime.baseUrl);
    expect(runtimeSection().text()).not.toContain('连接正常');
    expect(mocks.fetchAIHealth.mock.calls.map(([refresh]) => refresh)).toEqual([false]);
    expect(JSON.stringify(error.mock.calls)).not.toContain('保存失败');

    const retrySettings = deferred<AIModelSettings>();
    mocks.fetchAIModelSettings.mockReturnValueOnce(retrySettings.promise);
    mocks.fetchAIHealth.mockResolvedValueOnce(providerHealth('available', nextRuntime));
    await button(wrapper, '重新同步运行配置').trigger('click');
    await flushPromises();
    expect(runtimeSection().find('.ollama-status').exists()).toBe(false);
    expect(mocks.fetchAIHealth.mock.calls.map(([refresh]) => refresh)).toEqual([false]);

    retrySettings.resolve(settings(nextRuntime));
    await flushPromises();
    expect(runtimeSection().text()).toContain(nextRuntime.baseUrl);
    expect(runtimeSection().text()).toContain('连接正常');
    expect(runtimeSection().text()).not.toContain('运行配置未同步');
    expect(mocks.fetchAIHealth.mock.calls.map(([refresh]) => refresh)).toEqual([false, true]);
    expect(mocks.saveSystemAIConfig).toHaveBeenCalledTimes(1);
  });

  it('shows_saved_but_connection_failed_without_reopening_sensitive_dialog', async () => {
    const success = vi.spyOn(ElMessage, 'success');
    const error = vi.spyOn(ElMessage, 'error');
    const wrapper = await mountPage();
    mocks.fetchAIHealth.mockRejectedValueOnce({
      response: { data: { error: { code: 'AI_CONNECT_TIMEOUT' } } },
    });
    mocks.fetchAIHealth.mockRejectedValueOnce(new Error('health cache unavailable'));

    await button(wrapper, '保存服务器配置').trigger('click');
    await flushPromises();
    await wrapper.get('input[data-testid="admin-password"]').setValue('synthetic-admin-password');
    await wrapper.get('input[data-testid="upgrade-password"]').setValue('synthetic-upgrade-password');
    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();

    expect(success).toHaveBeenCalledWith('服务器 AI 配置已保存');
    expect(error).toHaveBeenCalledWith(expect.stringContaining('连接 AI 服务超时'));
    expect(success.mock.invocationCallOrder[0]).toBeLessThan(error.mock.invocationCallOrder[0]);
    expect(mocks.fetchAIModelSettings).toHaveBeenCalledTimes(2);
    expect(mocks.fetchAIHealth.mock.calls.map(([refresh]) => refresh)).toEqual([false, true, false]);
    expect(wrapper.text()).toContain('连接异常');
    expect(wrapper.text()).toContain('连接 AI 服务超时');
    expect(document.body.querySelector('[data-testid="auth-dialog"] .el-dialog')).toBeNull();
    expect(JSON.stringify(error.mock.calls)).not.toContain('保存失败');
  });

  it('keeps_non_ai_settings_usable_when_server_config_load_fails', async () => {
    mocks.fetchSystemAIConfig.mockRejectedValueOnce(new Error('server config unavailable'));
    const wrapper = await mountPage();

    expect(mocks.fetchSystemAIConfig).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain('外部检索');
    expect(wrapper.text()).toContain('备份设置');
    expect(button(wrapper, '保存设置').attributes('disabled')).toBeUndefined();
    expect(mocks.fetchAIModelSettings).toHaveBeenCalledTimes(1);
    expect(mocks.fetchExternalSearchSettings).toHaveBeenCalledTimes(1);
  });

  it('keeps_account_ai_preferences_available_without_server_controls_for_members', async () => {
    authState.isAdmin = false;
    const wrapper = await mountPage();

    expect(wrapper.findComponent(ServerAISettingsPanel).exists()).toBe(false);
    expect(wrapper.text()).not.toContain('保存服务器配置');
    expect(wrapper.text()).toContain('当前运行状态');
    expect(wrapper.text()).toContain('当前账号 AI 偏好');
    expect(wrapper.text()).toContain('账号偏好仅调整服务商、Ollama 地址和默认模型；服务器 AI 总开关、可信地址、Access 凭据、TLS 和超时由管理员统一管理。');
    expect(button(wrapper, '保存设置').attributes('disabled')).toBeUndefined();
  });

  it('waits_for_ai_settings_before_reading_process_health', async () => {
    const pendingSettings = deferred<AIModelSettings>();
    mocks.fetchAIModelSettings.mockReturnValueOnce(pendingSettings.promise);
    const wrapper = mount(SettingsPage, { global: { plugins: [ElementPlus] } });
    await flushPromises();

    expect(mocks.fetchAIHealth).not.toHaveBeenCalled();

    pendingSettings.resolve(settings());
    await flushPromises();

    expect(mocks.fetchAIHealth).toHaveBeenCalledTimes(1);
    expect(mocks.fetchAIHealth).toHaveBeenCalledWith(false);
    expect(wrapper.text()).toContain(currentRuntime.baseUrl);
  });

  it('binds_initial_health_failure_to_the_resolved_account_runtime', async () => {
    const pendingSettings = deferred<AIModelSettings>();
    mocks.fetchAIModelSettings.mockReturnValueOnce(pendingSettings.promise);
    mocks.fetchAIHealth.mockRejectedValueOnce({
      response: { data: { error: { code: 'AI_CONNECT_TIMEOUT' } } },
    });
    const wrapper = mount(SettingsPage, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(mocks.fetchAIHealth).not.toHaveBeenCalled();

    pendingSettings.resolve(settings());
    await flushPromises();

    expect(wrapper.text()).toContain('连接异常');
    expect(wrapper.text()).toContain(currentRuntime.baseUrl);
    expect(wrapper.text()).not.toContain(staleRuntime.baseUrl);
  });

  it('does_not_read_process_health_when_ai_settings_fail_to_load', async () => {
    const pendingSettings = deferred<AIModelSettings>();
    mocks.fetchAIModelSettings.mockReturnValueOnce(pendingSettings.promise);
    mount(SettingsPage, { global: { plugins: [ElementPlus] } });
    await flushPromises();

    pendingSettings.reject(new Error('settings unavailable'));
    await flushPromises();

    expect(mocks.fetchAIHealth).not.toHaveBeenCalled();
  });

  it('mounted_only_reads_cached_health_without_probe', async () => {
    await mountPage();

    expect(mocks.fetchAIHealth).toHaveBeenCalledTimes(1);
    expect(mocks.fetchAIHealth).toHaveBeenCalledWith(false);
    expect(mocks.testAIConnection).not.toHaveBeenCalled();
    expect(mocks.fetchAvailableModels).not.toHaveBeenCalled();
  });

  it('check_uses_refresh_true', async () => {
    const wrapper = await mountPage();

    await button(wrapper, '检查连接').trigger('click');
    await flushPromises();

    expect(mocks.fetchAIHealth).toHaveBeenLastCalledWith(true);
  });

  it('generate_cancel_does_not_call_api_and_confirm_calls_true', async () => {
    const wrapper = await mountPage();
    const confirm = vi.spyOn(ElMessageBox, 'confirm');
    confirm.mockRejectedValueOnce('cancel');

    await button(wrapper, '生成测试').trigger('click');
    await flushPromises();
    expect(mocks.testAIConnection).not.toHaveBeenCalled();

    confirm.mockResolvedValueOnce('confirm' as never);
    await button(wrapper, '生成测试').trigger('click');
    await flushPromises();
    expect(mocks.testAIConnection).toHaveBeenCalledWith(true);
  });

  it.each([
    ['检查连接', 'check'],
    ['普通测试', 'test'],
    ['生成测试', 'generate'],
  ])('%s failure replaces old healthy panel with cached error', async (label, action) => {
    const wrapper = await mountPage();
    if (action === 'generate') vi.spyOn(ElMessageBox, 'confirm').mockResolvedValueOnce('confirm' as never);
    if (action === 'check') {
      mocks.fetchAIHealth.mockRejectedValueOnce({ response: { data: { error: { code: 'AI_CONNECT_TIMEOUT' } } } });
    } else {
      mocks.testAIConnection.mockRejectedValueOnce({ response: { data: { error: { code: 'AI_CONNECT_TIMEOUT' } } } });
    }
    mocks.fetchAIHealth.mockResolvedValueOnce(providerHealth('unavailable'));

    await button(wrapper, label).trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('连接异常');
    expect(wrapper.text()).toContain('连接 AI 服务超时');
    expect(wrapper.text()).not.toContain('连接正常');
  });

  it('uses_a_local_sanitized_error_when_failed_health_cache_cannot_be_read', async () => {
    const wrapper = await mountPage();
    mocks.testAIConnection.mockRejectedValueOnce({
      response: { data: { error: { code: 'AI_RESPONSE_TIMEOUT', message: 'upstream detail' } } },
    });
    mocks.fetchAIHealth.mockRejectedValueOnce(new Error('cache unavailable'));

    await button(wrapper, '普通测试').trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('连接异常');
    expect(wrapper.text()).toContain('AI 模型响应超时，模型可能仍在启动，请稍后重试。');
    expect(wrapper.text()).toContain(currentRuntime.baseUrl);
    expect(wrapper.text()).not.toContain('upstream detail');
    expect(wrapper.text()).not.toContain('AI 服务连接正常');
  });

  it('discards_stale_process_health_from_another_runtime', async () => {
    mocks.fetchAIHealth.mockResolvedValueOnce(providerHealth('available', staleRuntime));

    const wrapper = await mountPage();

    expect(wrapper.text()).toContain(currentRuntime.baseUrl);
    expect(wrapper.text()).toContain('尚未检查');
    expect(wrapper.text()).not.toContain(staleRuntime.baseUrl);
    expect(wrapper.text()).not.toContain('0.12.6');
  });

  it('invalidates_old_health_after_saving_a_changed_runtime', async () => {
    const nextRuntime = { ...currentRuntime, baseUrl: 'https://changed.example.com', defaultModel: 'changed-model' };
    mocks.saveAIModelSettings.mockResolvedValueOnce(settings(nextRuntime));
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain('0.12.6');

    await button(wrapper, '保存设置').trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain(nextRuntime.baseUrl);
    expect(wrapper.text()).toContain('尚未检查');
    expect(wrapper.text()).not.toContain('0.12.6');
    expect(mocks.saveLocalSettings).toHaveBeenCalledWith(expect.objectContaining({
      ollamaBaseUrl: nextRuntime.baseUrl,
      defaultModel: nextRuntime.defaultModel,
    }));
  });

  it('applies_ai_save_immediately_when_external_save_later_fails', async () => {
    const nextRuntime = { ...currentRuntime, baseUrl: 'https://saved-ai.example.com', defaultModel: 'saved-ai-model' };
    const aiSave = deferred<AIModelSettings>();
    const externalSave = deferred<{ providers: [] }>();
    mocks.saveAIModelSettings.mockReturnValueOnce(aiSave.promise);
    mocks.saveExternalSearchSettings.mockReturnValueOnce(externalSave.promise);
    const warning = vi.spyOn(ElMessage, 'warning');
    const wrapper = await mountPage();

    await button(wrapper, '保存设置').trigger('click');
    aiSave.resolve(settings(nextRuntime));
    await flushPromises();

    expect(wrapper.text()).toContain(nextRuntime.baseUrl);
    expect(wrapper.text()).toContain('尚未检查');
    expect(wrapper.text()).not.toContain('0.12.6');

    externalSave.reject(new Error('external failed'));
    await flushPromises();
    expect(warning).toHaveBeenCalledWith('AI 配置已保存，外部检索设置保存失败');
  });

  it('applies_external_save_when_ai_save_later_fails', async () => {
    const aiSave = deferred<AIModelSettings>();
    const externalSave = deferred<{
      providers: Array<{
        provider: 'google_books';
        enabled: boolean;
        apiKey: string;
        extra: string;
        note: string;
        hasApiKey: boolean;
        hasExtra: boolean;
      }>;
    }>();
    mocks.saveAIModelSettings.mockReturnValueOnce(aiSave.promise);
    mocks.saveExternalSearchSettings.mockReturnValueOnce(externalSave.promise);
    const warning = vi.spyOn(ElMessage, 'warning');
    const wrapper = await mountPage();

    await button(wrapper, '保存设置').trigger('click');
    externalSave.resolve({
      providers: [{
        provider: 'google_books',
        enabled: true,
        apiKey: '',
        extra: '',
        note: '外部检索新配置已应用',
        hasApiKey: false,
        hasExtra: false,
      }],
    });
    await flushPromises();

    expect(wrapper.text()).toContain('外部检索新配置已应用');
    aiSave.reject(new Error('ai failed'));
    await flushPromises();

    expect(wrapper.text()).toContain(currentRuntime.baseUrl);
    expect(wrapper.text()).toContain('0.12.6');
    expect(warning).toHaveBeenCalledWith('外部检索设置已保存，AI 配置保存失败');
    expect(mocks.saveLocalSettings).toHaveBeenCalledWith(expect.objectContaining({
      ollamaBaseUrl: 'http://localhost:11434',
      defaultModel: '',
    }));
    expect(mocks.saveLocalSettings).not.toHaveBeenCalledWith(expect.objectContaining({
      ollamaBaseUrl: currentRuntime.baseUrl,
      defaultModel: currentRuntime.defaultModel,
    }));
  });

  it('keeps_backend_result_messages_when_local_preferences_fail_to_save', async () => {
    mocks.saveLocalSettings.mockImplementationOnce(() => {
      throw new Error('sensitive local storage detail');
    });
    const success = vi.spyOn(ElMessage, 'success');
    const warning = vi.spyOn(ElMessage, 'warning');
    const wrapper = await mountPage();

    await button(wrapper, '保存设置').trigger('click');
    await flushPromises();

    expect(success).toHaveBeenCalledWith('设置已保存到当前账号');
    expect(warning).toHaveBeenCalledWith('服务器设置已处理，但本地偏好保存失败');
    expect(JSON.stringify(warning.mock.calls)).not.toContain('sensitive local storage detail');
  });

  it('refreshing_models_does_not_replace_the_saved_default_model', async () => {
    const wrapper = await mountPage();

    await button(wrapper, '刷新模型列表').trigger('click');
    await flushPromises();
    await button(wrapper, '保存设置').trigger('click');
    await flushPromises();

    expect(mocks.saveAIModelSettings).toHaveBeenCalledWith(expect.objectContaining({
      defaultModel: 'selected-model',
    }));
  });
});
