import ElementPlus, { ElMessageBox } from 'element-plus';
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
