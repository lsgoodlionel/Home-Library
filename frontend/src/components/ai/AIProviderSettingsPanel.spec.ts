import ElementPlus, { ElMessageBox } from 'element-plus';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AIProviderHealthStatus } from '@/types/ai';
import type { AIModelSettings, AIProviderConfig } from '@/types/settings';
import AIProviderSettingsPanel from './AIProviderSettingsPanel.vue';

const mocks = vi.hoisted(() => ({
  fetchAIModelSettings: vi.fn(),
  saveAIModelSettings: vi.fn(),
  testAIProvider: vi.fn(),
  fetchAIProviderModels: vi.fn(),
  generateAIProviderTest: vi.fn(),
}));

vi.mock('@/api/settings', () => ({
  fetchAIModelSettings: mocks.fetchAIModelSettings,
  saveAIModelSettings: mocks.saveAIModelSettings,
}));

vi.mock('@/api/ai', () => ({
  testAIProvider: mocks.testAIProvider,
  fetchAIProviderModels: mocks.fetchAIProviderModels,
  generateAIProviderTest: mocks.generateAIProviderTest,
}));

function provider(overrides: Partial<AIProviderConfig> & Pick<AIProviderConfig, 'provider'>): AIProviderConfig {
  return {
    enabled: true,
    baseUrl: `https://${overrides.provider}.example.test`,
    defaultModel: `${overrides.provider}-saved-model`,
    note: '',
    hasApiKey: overrides.provider !== 'ollama',
    credentialState: 'configured',
    ...overrides,
  };
}

function settings(): AIModelSettings {
  return {
    aiEnabled: true,
    activeProvider: 'openai',
    defaultModel: 'openai-saved-model',
    providers: [
      provider({ provider: 'ollama', hasApiKey: false }),
      provider({ provider: 'openai' }),
      provider({ provider: 'gemini', enabled: false, credentialState: 'missing', hasApiKey: false }),
    ],
    ollamaRuntime: {
      enabled: true,
      baseUrl: 'https://ollama.example.test',
      defaultModel: 'ollama-saved-model',
      connectTimeoutSeconds: 20,
      readTimeoutSeconds: 180,
      verifyTls: true,
      accessConfigured: false,
      usesAccess: false,
    },
  };
}

function health(providerKey: AIProviderConfig['provider'], models: string[] = []): AIProviderHealthStatus {
  return {
    provider: providerKey,
    status: 'available',
    message: `${providerKey} 操作完成`,
    checkedAt: '2026-10-21T00:00:00Z',
    effectiveModel: `${providerKey}-saved-model`,
    safeBaseUrl: `https://${providerKey}.example.test`,
    credentialState: 'configured',
    models: models.map((name) => ({ provider: providerKey, id: name, name })),
    details: {},
  };
}

interface ButtonContainer {
  findAll(selector: string): Array<{
    text(): string;
    trigger(event: string): Promise<void>;
    attributes(name: string): string | undefined;
  }>;
}

function button(wrapper: ButtonContainer, label: string) {
  const found = wrapper.findAll('button').find((item) => item.text().includes(label));
  if (!found) throw new Error(`未找到按钮：${label}`);
  return found;
}

function providerPanel(wrapper: VueWrapper, key: string) {
  return wrapper.get(`[data-provider="${key}"]`);
}

async function mountPanel() {
  const wrapper = mount(AIProviderSettingsPanel, { global: { plugins: [ElementPlus] } });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchAIModelSettings.mockResolvedValue(settings());
  mocks.saveAIModelSettings.mockImplementation(async (value: AIModelSettings) => ({
    ...value,
    providers: value.providers.map((item) => ({ ...item, apiKey: undefined, clearApiKey: false })),
  }));
  mocks.testAIProvider.mockResolvedValue(health('openai'));
  mocks.fetchAIProviderModels.mockImplementation(async (key: AIProviderConfig['provider']) => health(key, [`${key}-remote-model`]));
  mocks.generateAIProviderTest.mockResolvedValue(health('openai'));
});

describe('AIProviderSettingsPanel', () => {
  it('performs zero automatic provider operations when account AI is off', async () => {
    mocks.fetchAIModelSettings.mockResolvedValueOnce({ ...settings(), aiEnabled: false });
    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain('当前账号 AI 配置');
    expect(mocks.testAIProvider).not.toHaveBeenCalled();
    expect(mocks.fetchAIProviderModels).not.toHaveBeenCalled();
    expect(mocks.generateAIProviderTest).not.toHaveBeenCalled();
  });

  it('keeps Ollama editable and blocks disabling the active provider until switched or AI is off', async () => {
    const wrapper = await mountPanel();

    expect(providerPanel(wrapper, 'ollama').get('[data-testid="provider-enabled"] input').attributes('disabled')).toBeUndefined();
    expect(providerPanel(wrapper, 'openai').get('[data-testid="provider-enabled"] input').attributes('disabled')).toBeDefined();

    await wrapper.get('[data-testid="account-ai-enabled"]').trigger('click');
    expect(providerPanel(wrapper, 'openai').get('[data-testid="provider-enabled"] input').attributes('disabled')).toBeUndefined();
  });

  it('offers only enabled valid providers as the active provider', async () => {
    const loaded = settings();
    loaded.providers.push(provider({ provider: 'deepseek', credentialState: 'missing', hasApiKey: false }));
    mocks.fetchAIModelSettings.mockResolvedValueOnce(loaded);
    const wrapper = await mountPanel();

    const labels = wrapper.findAllComponents({ name: 'ElOption' }).map((option) => option.props('label'));
    expect(labels).toEqual(['Ollama', 'OpenAI']);
  });

  it('preserves, replaces, and explicitly clears a saved key', async () => {
    const wrapper = await mountPanel();
    const openai = providerPanel(wrapper, 'openai');

    await button(wrapper, '保存账号 AI 配置').trigger('click');
    await flushPromises();
    let saved = mocks.saveAIModelSettings.mock.calls[0][0] as AIModelSettings;
    expect(saved.providers.find((item) => item.provider === 'openai')).toMatchObject({ apiKey: '', clearApiKey: false });

    await openai.get('input[data-testid="provider-api-key"]').setValue('replacement-key');
    await button(wrapper, '保存账号 AI 配置').trigger('click');
    await flushPromises();
    saved = mocks.saveAIModelSettings.mock.calls[1][0] as AIModelSettings;
    expect(saved.providers.find((item) => item.provider === 'openai')).toMatchObject({ apiKey: 'replacement-key', clearApiKey: false });

    await providerPanel(wrapper, 'openai').get('[data-testid="clear-api-key"] input').setValue(true);
    await wrapper.get('[data-testid="account-ai-enabled"]').trigger('click');
    await button(wrapper, '保存账号 AI 配置').trigger('click');
    await flushPromises();
    saved = mocks.saveAIModelSettings.mock.calls[2][0] as AIModelSettings;
    expect(saved.providers.find((item) => item.provider === 'openai')).toMatchObject({ apiKey: '', clearApiKey: true });
  });

  it('isolates provider drafts and ignores a late model response from another provider', async () => {
    let resolveOpenAI!: (value: AIProviderHealthStatus) => void;
    mocks.fetchAIProviderModels.mockImplementationOnce(() => new Promise((resolve) => { resolveOpenAI = resolve; }));
    const wrapper = await mountPanel();
    const openai = providerPanel(wrapper, 'openai');
    const ollama = providerPanel(wrapper, 'ollama');

    await openai.get('input[data-testid="provider-api-key"]').setValue('openai-draft-key');
    await openai.get('[data-testid="provider-model"] input').setValue('openai-draft-model');
    await button(openai, '刷新模型').trigger('click');
    await ollama.get('input[data-testid="provider-address"]').setValue('https://ollama-draft.example.test');
    await button(ollama, '刷新模型').trigger('click');
    await flushPromises();
    resolveOpenAI(health('openai', ['late-openai-model']));
    await flushPromises();

    expect((openai.get('input[data-testid="provider-api-key"]').element as HTMLInputElement).value).toBe('openai-draft-key');
    expect((ollama.get('input[data-testid="provider-address"]').element as HTMLInputElement).value).toBe('https://ollama-draft.example.test');
    expect(ollama.text()).toContain('ollama 操作完成');
    expect(ollama.text()).not.toContain('openai 操作完成');
  });

  it('keeps test independent from save and only clears drafts after save succeeds', async () => {
    const wrapper = await mountPanel();
    const openai = providerPanel(wrapper, 'openai');
    await openai.get('input[data-testid="provider-api-key"]').setValue('pending-key');

    await button(openai, '测试连接').trigger('click');
    await flushPromises();
    expect(mocks.testAIProvider).toHaveBeenCalledWith('openai', expect.objectContaining({ apiKey: 'pending-key' }));
    expect(mocks.saveAIModelSettings).not.toHaveBeenCalled();
    expect((openai.get('input[data-testid="provider-api-key"]').element as HTMLInputElement).value).toBe('pending-key');

    mocks.saveAIModelSettings.mockRejectedValueOnce(new Error('save failed'));
    await button(wrapper, '保存账号 AI 配置').trigger('click');
    await flushPromises();
    expect((openai.get('input[data-testid="provider-api-key"]').element as HTMLInputElement).value).toBe('pending-key');

    await button(wrapper, '保存账号 AI 配置').trigger('click');
    await flushPromises();
    expect((providerPanel(wrapper, 'openai').get('input[data-testid="provider-api-key"]').element as HTMLInputElement).value).toBe('');
  });

  it('requires explicit cost confirmation before generation and sends no request on cancel', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValueOnce('cancel');
    const wrapper = await mountPanel();
    const openai = providerPanel(wrapper, 'openai');

    await button(openai, '生成测试').trigger('click');
    await flushPromises();
    expect(confirm).toHaveBeenCalledWith(
      expect.stringMatching(/费用|额度/),
      '确认生成测试',
      expect.objectContaining({ type: 'warning' }),
    );
    expect(mocks.generateAIProviderTest).not.toHaveBeenCalled();

    confirm.mockResolvedValueOnce('confirm' as never);
    await button(openai, '生成测试').trigger('click');
    await flushPromises();
    expect(mocks.generateAIProviderTest).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['account off', async (wrapper: VueWrapper) => wrapper.get('[data-testid="account-ai-enabled"]').trigger('click')],
    ['provider disabled', async (wrapper: VueWrapper) => providerPanel(wrapper, 'ollama').get('[data-testid="provider-enabled"]').trigger('click')],
    ['address changed', async (wrapper: VueWrapper) => providerPanel(wrapper, 'openai').get('input[data-testid="provider-address"]').setValue('https://changed.example.test')],
    ['key changed', async (wrapper: VueWrapper) => providerPanel(wrapper, 'openai').get('input[data-testid="provider-api-key"]').setValue('changed-key')],
    ['model changed', async (wrapper: VueWrapper) => providerPanel(wrapper, 'openai').findComponent({ name: 'ElSelect' }).setValue('changed-model')],
    ['clear changed', async (wrapper: VueWrapper) => providerPanel(wrapper, 'openai').get('[data-testid="clear-api-key"] input').setValue(true)],
  ])('drops a pending response after %s', async (_label, mutate) => {
    let resolve!: (value: AIProviderHealthStatus) => void;
    const pending = new Promise<AIProviderHealthStatus>((resolvePromise) => { resolve = resolvePromise; });
    mocks.fetchAIProviderModels.mockImplementationOnce(() => pending);
    const wrapper = await mountPanel();
    const target = _label === 'provider disabled' ? providerPanel(wrapper, 'ollama') : providerPanel(wrapper, 'openai');

    await button(target, '刷新模型').trigger('click');
    await mutate(wrapper);
    resolve(health(_label === 'provider disabled' ? 'ollama' : 'openai', ['stale-model']));
    await flushPromises();

    expect(wrapper.text()).not.toContain('stale-model');
    expect(wrapper.text()).not.toContain(`${_label === 'provider disabled' ? 'ollama' : 'openai'} 操作完成`);
  });

  it('drops pending responses after unmount without affecting another provider', async () => {
    let resolve!: (value: AIProviderHealthStatus) => void;
    mocks.fetchAIProviderModels.mockImplementationOnce(() => new Promise((resolvePromise) => { resolve = resolvePromise; }));
    const wrapper = await mountPanel();
    await button(providerPanel(wrapper, 'openai'), '刷新模型').trigger('click');
    await button(providerPanel(wrapper, 'ollama'), '刷新模型').trigger('click');
    await flushPromises();
    expect(providerPanel(wrapper, 'ollama').text()).toContain('ollama 操作完成');

    wrapper.unmount();
    resolve(health('openai', ['stale-model']));
    await flushPromises();
    expect(mocks.fetchAIProviderModels).toHaveBeenCalledTimes(2);
  });

  it.each(['测试连接', '刷新模型', '生成测试'])('sends no manual %s request while local account AI is off', async (label) => {
    const loaded = settings();
    loaded.aiEnabled = false;
    mocks.fetchAIModelSettings.mockResolvedValueOnce(loaded);
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never);
    const wrapper = await mountPanel();
    await button(providerPanel(wrapper, 'openai'), label).trigger('click');
    await flushPromises();
    expect(mocks.testAIProvider).not.toHaveBeenCalled();
    expect(mocks.fetchAIProviderModels).not.toHaveBeenCalled();
    expect(mocks.generateAIProviderTest).not.toHaveBeenCalled();
  });

  it.each(['account off', 'provider off', 'model changed', 'key changed', 'unmount'])('does not generate after pending confirmation becomes stale: %s', async (change) => {
    let confirm!: (value: string) => void;
    vi.spyOn(ElMessageBox, 'confirm').mockImplementationOnce(() => new Promise((resolve) => {
      confirm = resolve;
    }) as never);
    const wrapper = await mountPanel();
    const key = change === 'provider off' ? 'ollama' : 'openai';
    const panel = providerPanel(wrapper, key);
    void button(panel, '生成测试').trigger('click');
    await flushPromises();
    expect(mocks.generateAIProviderTest).not.toHaveBeenCalled();
    if (change === 'account off') await wrapper.get('[data-testid="account-ai-enabled"]').trigger('click');
    else if (change === 'provider off') await panel.get('[data-testid="provider-enabled"]').trigger('click');
    else if (change === 'model changed') await panel.findComponent({ name: 'ElSelect' }).setValue('changed-model');
    else if (change === 'key changed') await panel.get('input[data-testid="provider-api-key"]').setValue('changed-key');
    else wrapper.unmount();
    confirm('confirm');
    await flushPromises();
    expect(mocks.generateAIProviderTest).not.toHaveBeenCalled();
  });

  it('uses one generation confirmation and request while the provider mutex is held', async () => {
    let settleConfirm!: (value: string) => void;
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockImplementationOnce(() => new Promise((resolve) => {
      settleConfirm = resolve;
    }) as never);
    const wrapper = await mountPanel();
    const openai = providerPanel(wrapper, 'openai');
    const generate = button(openai, '生成测试');

    void generate.trigger('click');
    void generate.trigger('click');
    await flushPromises();
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(generate.attributes('disabled')).toBeDefined();
    expect(mocks.generateAIProviderTest).not.toHaveBeenCalled();

    settleConfirm('confirm');
    await flushPromises();
    expect(mocks.generateAIProviderTest).toHaveBeenCalledTimes(1);
  });

  it('releases the generation mutex after cancel so generation can be retried', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm')
      .mockRejectedValueOnce('cancel')
      .mockResolvedValueOnce('confirm' as never);
    const wrapper = await mountPanel();
    const openai = providerPanel(wrapper, 'openai');

    await button(openai, '生成测试').trigger('click');
    await flushPromises();
    await button(openai, '生成测试').trigger('click');
    await flushPromises();

    expect(confirm).toHaveBeenCalledTimes(2);
    expect(mocks.generateAIProviderTest).toHaveBeenCalledTimes(1);
  });

  it('releases the generation mutex after confirmation failure', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm')
      .mockRejectedValueOnce(new Error('dialog failed'))
      .mockResolvedValueOnce('confirm' as never);
    const wrapper = await mountPanel();
    const openai = providerPanel(wrapper, 'openai');

    await button(openai, '生成测试').trigger('click');
    await flushPromises();
    await button(openai, '生成测试').trigger('click');
    await flushPromises();

    expect(confirm).toHaveBeenCalledTimes(2);
    expect(mocks.generateAIProviderTest).toHaveBeenCalledTimes(1);
  });
});
