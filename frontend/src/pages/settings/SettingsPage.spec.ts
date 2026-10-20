import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AIHealthStatus } from '@/types/ai';
import type { AIModelSettings, OllamaRuntimeStatus } from '@/types/settings';
import SettingsPage from './SettingsPage.vue';

const mocks = vi.hoisted(() => ({
  fetchAIHealth: vi.fn(),
  testAIConnection: vi.fn(),
  fetchAvailableModels: vi.fn(),
  fetchAIModelSettings: vi.fn(),
  saveAIModelSettings: vi.fn(),
  fetchExternalSearchSettings: vi.fn(),
  saveExternalSearchSettings: vi.fn(),
  fetchAppVersion: vi.fn(),
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
  loadLocalSettings: vi.fn(() => ({
    ollamaBaseUrl: 'http://localhost:11434',
    defaultModel: '',
    externalSearchEnabled: true,
    externalProviderOrder: ['nlc', 'isbn_work', 'douban', 'google_books', 'open_library'],
  })),
  saveAIModelSettings: mocks.saveAIModelSettings,
  saveExternalSearchSettings: mocks.saveExternalSearchSettings,
  saveLocalSettings: vi.fn(),
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
  useAuthStore: () => ({ isAdmin: true }),
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

function settings(runtime = currentRuntime): AIModelSettings {
  return {
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
    }],
    ollamaRuntime: runtime,
  };
}

function health(
  status: AIHealthStatus['status'] = 'healthy',
  runtime = currentRuntime,
): AIHealthStatus {
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
  mocks.fetchAppVersion.mockResolvedValue({ appName: 'Home Library', version: 'test', environment: 'test' });
  mocks.fetchExternalSearchSettings.mockResolvedValue({ providers: [] });
  mocks.saveExternalSearchSettings.mockResolvedValue({ providers: [] });
  mocks.fetchAIModelSettings.mockResolvedValue(settings());
  mocks.saveAIModelSettings.mockResolvedValue(settings());
  mocks.fetchAIHealth.mockResolvedValue(health());
  mocks.testAIConnection.mockResolvedValue(health());
  mocks.fetchAvailableModels.mockResolvedValue([{ name: 'first-model' }]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('SettingsPage AI status orchestration', () => {
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
    mocks.fetchAIHealth.mockResolvedValueOnce(health('error'));

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
    mocks.fetchAIHealth.mockResolvedValueOnce(health('healthy', staleRuntime));

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
