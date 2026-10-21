import ElementPlus, { ElMessage } from 'element-plus';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AIProviderSettingsPanel from '@/components/ai/AIProviderSettingsPanel.vue';
import CurrentAIStatus from '@/components/ai/CurrentAIStatus.vue';
import ServerAISettingsPanel from '@/components/ai/ServerAISettingsPanel.vue';
import type { AIProviderHealthStatus } from '@/types/ai';
import type { AIModelSettings, SystemAIConfig } from '@/types/settings';
import SettingsPage from './SettingsPage.vue';

const authState = vi.hoisted(() => ({ isAdmin: true }));
const mocks = vi.hoisted(() => ({
  fetchAIHealth: vi.fn(), fetchAIProviderModels: vi.fn(), testAIProvider: vi.fn(), generateAIProviderTest: vi.fn(),
  fetchAIModelSettings: vi.fn(), saveAIModelSettings: vi.fn(), fetchExternalSearchSettings: vi.fn(),
  saveExternalSearchSettings: vi.fn(), saveLocalSettings: vi.fn(), fetchAppVersion: vi.fn(),
  fetchSystemAIConfig: vi.fn(), fetchSystemAIModels: vi.fn(), saveSystemAIConfig: vi.fn(),
  resetSystemAIConfig: vi.fn(), testSystemAIConfig: vi.fn(),
}));

vi.mock('@/api/ai', () => ({
  classifyBook: vi.fn(), fetchAIHealth: mocks.fetchAIHealth, fetchAIProviderModels: mocks.fetchAIProviderModels,
  testAIProvider: mocks.testAIProvider, generateAIProviderTest: mocks.generateAIProviderTest,
}));
vi.mock('@/api/settings', () => ({
  DEFAULT_EXTERNAL_PROVIDER_ORDER: ['nlc', 'isbn_work', 'douban', 'google_books', 'open_library'],
  EXTERNAL_BOOK_PROVIDERS: [
    { key: 'nlc', name: 'NLC', description: '' }, { key: 'isbn_work', name: 'ISBN Work', description: '' },
    { key: 'douban', name: '豆瓣', description: '' }, { key: 'google_books', name: 'Google Books', description: '' },
    { key: 'open_library', name: 'Open Library', description: '' },
  ],
  fetchAppVersion: mocks.fetchAppVersion, fetchAIModelSettings: mocks.fetchAIModelSettings,
  saveAIModelSettings: mocks.saveAIModelSettings, fetchExternalSearchSettings: mocks.fetchExternalSearchSettings,
  saveExternalSearchSettings: mocks.saveExternalSearchSettings, saveLocalSettings: mocks.saveLocalSettings,
  fetchSystemAIConfig: mocks.fetchSystemAIConfig, fetchSystemAIModels: mocks.fetchSystemAIModels,
  saveSystemAIConfig: mocks.saveSystemAIConfig, resetSystemAIConfig: mocks.resetSystemAIConfig,
  testSystemAIConfig: mocks.testSystemAIConfig, validateExternalProvider: vi.fn(),
  loadLocalSettings: vi.fn(() => ({
    ollamaBaseUrl: 'http://localhost:11434', defaultModel: 'qwen', externalSearchEnabled: true,
    externalProviderOrder: ['nlc', 'isbn_work', 'douban', 'google_books', 'open_library'],
  })),
}));
vi.mock('@/api/books', () => ({
  bookDetailToForm: vi.fn(), getBook: vi.fn(), getBooks: vi.fn(), getCategoryOptions: vi.fn(), updateBook: vi.fn(),
}));
vi.mock('@/api/importExport', () => ({
  confirmBooksImport: vi.fn(), downloadBooksExport: vi.fn(), downloadImportTemplate: vi.fn(), previewBooksImport: vi.fn(),
}));
vi.mock('@/stores/auth', () => ({ useAuthStore: () => authState }));

const accountSettings: AIModelSettings = {
  aiEnabled: true, activeProvider: 'ollama', defaultModel: 'qwen',
  providers: [{ provider: 'ollama', enabled: true, baseUrl: 'http://ollama.test', defaultModel: 'qwen', note: '', hasApiKey: false, credentialState: 'configured' }],
  ollamaRuntime: { enabled: true, baseUrl: 'http://ollama.test', defaultModel: 'qwen', connectTimeoutSeconds: 20, readTimeoutSeconds: 180, verifyTls: true, accessConfigured: false, usesAccess: false },
};
const providerHealth: AIProviderHealthStatus = {
  provider: 'ollama', status: 'available', message: '连接正常', checkedAt: '2026-10-21T00:00:00Z',
  effectiveModel: 'qwen', safeBaseUrl: 'http://ollama.test', credentialState: 'configured', models: [], details: {},
};
const serverConfig: SystemAIConfig = {
  enabled: true, defaultBaseUrl: 'http://ollama.test', trustedBaseUrl: 'http://ollama.test', defaultModel: 'qwen',
  connectTimeoutSeconds: 20, readTimeoutSeconds: 180, verifyTls: true,
  credentialState: { accessClientIdConfigured: false, accessClientSecretConfigured: false, credentialsUsable: true, source: 'environment' },
  configurationSource: 'environment', configVersion: 1,
};

function button(wrapper: VueWrapper, label: string) {
  const found = wrapper.findAll('button').find((item) => item.text().includes(label));
  if (!found) throw new Error(`未找到按钮：${label}`);
  return found;
}
async function mountPage() {
  const wrapper = mount(SettingsPage, { global: { plugins: [ElementPlus] } });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  authState.isAdmin = true;
  mocks.fetchAIModelSettings.mockResolvedValue(accountSettings);
  mocks.saveAIModelSettings.mockResolvedValue(accountSettings);
  mocks.fetchAIHealth.mockResolvedValue(providerHealth);
  mocks.fetchAIProviderModels.mockResolvedValue(providerHealth);
  mocks.fetchExternalSearchSettings.mockResolvedValue({ providers: [{ provider: 'google_books', enabled: true, apiKey: '', extra: '', note: 'Google', hasApiKey: false, hasExtra: false }] });
  mocks.saveExternalSearchSettings.mockResolvedValue({ providers: [{ provider: 'google_books', enabled: true, apiKey: '', extra: '', note: '已保存', hasApiKey: true, hasExtra: false }] });
  mocks.fetchAppVersion.mockResolvedValue({ appName: 'Home Library', version: 'test', environment: 'test' });
  mocks.fetchSystemAIConfig.mockResolvedValue(serverConfig);
  mocks.fetchSystemAIModels.mockResolvedValue([]);
});

describe('SettingsPage AI composition', () => {
  it('orders server gateway, current status, and account settings for admins without nested cards', async () => {
    const wrapper = await mountPage();
    const text = wrapper.get('[data-testid="ai-settings-sections"]').text();
    const serverIndex = text.indexOf('服务器 Ollama 网关');
    const statusIndex = text.indexOf('当前 AI 运行状态');
    const accountIndex = text.indexOf('当前账号 AI 配置');
    expect(serverIndex).toBeGreaterThanOrEqual(0);
    expect(statusIndex).toBeGreaterThan(serverIndex);
    expect(accountIndex).toBeGreaterThan(statusIndex);
    expect(wrapper.findAllComponents(ServerAISettingsPanel)).toHaveLength(1);
    expect(wrapper.findAllComponents(CurrentAIStatus)).toHaveLength(1);
    expect(wrapper.findAllComponents(AIProviderSettingsPanel)).toHaveLength(1);
    expect(wrapper.find('.ai-settings-sections .el-card').exists()).toBe(false);
  });

  it('hides only the server gateway for non-admin accounts', async () => {
    authState.isAdmin = false;
    const wrapper = await mountPage();
    expect(wrapper.findComponent(ServerAISettingsPanel).exists()).toBe(false);
    expect(wrapper.findComponent(CurrentAIStatus).exists()).toBe(true);
    expect(wrapper.findComponent(AIProviderSettingsPanel).exists()).toBe(true);
    expect(wrapper.text()).not.toContain('保存服务器配置');
    expect(wrapper.text()).toContain('账号 AI');
  });

  it('does not start provider operations when account AI is disabled', async () => {
    mocks.fetchAIModelSettings.mockResolvedValue({ ...accountSettings, aiEnabled: false });
    const wrapper = await mountPage();
    expect(wrapper.text()).toContain('当前账号未启用 AI');
    expect(mocks.fetchAIHealth).not.toHaveBeenCalled();
    expect(mocks.fetchAIProviderModels).not.toHaveBeenCalled();
  });

  it('preserves external-search saving without resaving account AI', async () => {
    const success = vi.spyOn(ElMessage, 'success');
    const wrapper = await mountPage();
    await button(wrapper, '保存设置').trigger('click');
    await flushPromises();
    expect(mocks.saveExternalSearchSettings).toHaveBeenCalledTimes(1);
    expect(mocks.saveAIModelSettings).not.toHaveBeenCalled();
    expect(mocks.saveLocalSettings).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain('已保存');
    expect(success).toHaveBeenCalledWith('外部检索设置已保存');
  });
});
