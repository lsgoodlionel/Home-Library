import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import * as aiApi from '@/api/ai';
import type { AIProviderHealthStatus } from '@/types/ai';
import CurrentAIStatus from './CurrentAIStatus.vue';

const baseStatus: AIProviderHealthStatus = {
  provider: 'openai',
  status: 'available',
  message: '连接正常',
  checkedAt: '2026-10-21T00:00:00Z',
  effectiveModel: 'gpt-5-mini',
  safeBaseUrl: 'https://api.openai.com/v1',
  credentialState: 'configured',
  models: [{ provider: 'openai', id: 'gpt-5-mini', name: 'GPT-5 mini' }],
  details: {},
};

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function mountStatus(props: Record<string, unknown>) {
  return mount(CurrentAIStatus, {
    props: {
      aiEnabled: true,
      provider: 'openai',
      model: 'gpt-5-mini',
      ...props,
    },
    global: {
      stubs: {
        ElAlert: { template: '<div class="alert">{{ title }}</div>', props: ['title'] },
        ElDescriptions: { template: '<dl><slot /></dl>' },
        ElDescriptionsItem: { template: '<div><dt>{{ label }}</dt><dd><slot /></dd></div>', props: ['label'] },
        ElTag: { template: '<span><slot /></span>' },
      },
    },
  });
}

afterEach(() => vi.restoreAllMocks());

describe('CurrentAIStatus', () => {
  it('distinguishes loading, unchecked, unavailable, available empty-model, and request error states', async () => {
    const pendingHealth = deferred<AIProviderHealthStatus>();
    const pendingModels = deferred<AIProviderHealthStatus>();
    vi.spyOn(aiApi, 'fetchAIHealth').mockReturnValueOnce(pendingHealth.promise);
    vi.spyOn(aiApi, 'fetchAIProviderModels').mockReturnValueOnce(pendingModels.promise);
    const loading = mountStatus({});
    expect(loading.text()).toContain('正在检查');
    expect(loading.text()).toContain('检查中');
    loading.unmount();

    vi.mocked(aiApi.fetchAIHealth).mockResolvedValueOnce({
      ...baseStatus,
      status: 'unchecked',
      message: '尚未检查',
    });
    vi.mocked(aiApi.fetchAIProviderModels).mockResolvedValueOnce({ ...baseStatus, models: [] });
    const unchecked = mountStatus({});
    await flushPromises();
    expect(unchecked.text()).toContain('尚未检查');
    expect(unchecked.text()).not.toContain('未发现可用模型');
    unchecked.unmount();

    vi.mocked(aiApi.fetchAIHealth).mockResolvedValueOnce({
      ...baseStatus,
      status: 'unavailable',
      message: '连接失败',
    });
    vi.mocked(aiApi.fetchAIProviderModels).mockResolvedValueOnce({ ...baseStatus, models: [] });
    const unavailable = mountStatus({});
    await flushPromises();
    expect(unavailable.text()).toContain('连接不可用');
    expect(unavailable.text()).not.toContain('尚未检查');
    expect(unavailable.text()).not.toContain('未发现可用模型');
    unavailable.unmount();

    vi.mocked(aiApi.fetchAIHealth).mockResolvedValueOnce(baseStatus);
    vi.mocked(aiApi.fetchAIProviderModels).mockResolvedValueOnce({ ...baseStatus, models: [] });
    const empty = mountStatus({});
    await flushPromises();
    expect(empty.text()).toContain('连接正常');
    expect(empty.text()).toContain('未发现可用模型，可手动输入模型名称');
    empty.unmount();

    vi.mocked(aiApi.fetchAIHealth).mockRejectedValueOnce(new Error('unsafe-marker'));
    vi.mocked(aiApi.fetchAIProviderModels).mockResolvedValueOnce(baseStatus);
    const failed = mountStatus({});
    await flushPromises();
    expect(failed.text()).toContain('检查失败');
    expect(failed.text()).toContain('AI 服务暂时不可用');
    expect(failed.text()).not.toContain('unsafe-marker');
  });

  it('shows Ollama-only runtime details only for Ollama', async () => {
    vi.spyOn(aiApi, 'fetchAIProviderModels')
      .mockResolvedValueOnce({ ...baseStatus, provider: 'ollama', models: [] })
      .mockResolvedValueOnce(baseStatus);
    vi.spyOn(aiApi, 'fetchAIHealth').mockResolvedValue({
      ...baseStatus,
      provider: 'ollama',
      effectiveModel: 'qwen3:8b',
      details: {
        version: '0.12.6',
        installed_model_count: 3,
        running_model_count: 1,
        uses_access: true,
      },
    });
    const ollama = mountStatus({ provider: 'ollama', model: 'qwen3:8b' });
    await flushPromises();
    expect(ollama.text()).toContain('Ollama 版本');
    expect(ollama.text()).toContain('0.12.6');
    expect(ollama.text()).toContain('已安装模型');

    vi.mocked(aiApi.fetchAIHealth).mockResolvedValue(baseStatus);
    const cloud = mountStatus({});
    await flushPromises();
    expect(cloud.text()).toContain('OpenAI');
    expect(cloud.text()).toContain('GPT-5 mini');
    expect(cloud.text()).toContain('已配置');
    expect(cloud.text()).not.toContain('Ollama 版本');
    expect(cloud.text()).not.toContain('已安装模型');
  });

  it('does not check health or models while account AI is off', async () => {
    const health = vi.spyOn(aiApi, 'fetchAIHealth').mockResolvedValue(baseStatus);
    const models = vi.spyOn(aiApi, 'fetchAIProviderModels').mockResolvedValue(baseStatus);

    const wrapper = mountStatus({ aiEnabled: false });
    await flushPromises();

    expect(wrapper.text()).toContain('当前账号未启用 AI');
    expect(health).not.toHaveBeenCalled();
    expect(models).not.toHaveBeenCalled();
  });

  it('renders a stable Chinese message instead of raw request errors', async () => {
    vi.spyOn(aiApi, 'fetchAIHealth').mockRejectedValue(new Error('draft-key-sensitive-marker'));
    vi.spyOn(aiApi, 'fetchAIProviderModels').mockResolvedValue(baseStatus);

    const wrapper = mountStatus({});
    await flushPromises();

    expect(wrapper.text()).toContain('AI 服务暂时不可用');
    expect(wrapper.text()).not.toContain('draft-key-sensitive-marker');
  });

  it('ignores stale model responses after switching providers and after unmount', async () => {
    vi.spyOn(aiApi, 'fetchAIHealth').mockResolvedValue(baseStatus);
    let resolveOpenAI!: (value: AIProviderHealthStatus) => void;
    let resolveGemini!: (value: AIProviderHealthStatus) => void;
    vi.spyOn(aiApi, 'fetchAIProviderModels')
      .mockReturnValueOnce(new Promise((resolve) => { resolveOpenAI = resolve; }))
      .mockReturnValueOnce(new Promise((resolve) => { resolveGemini = resolve; }));

    const wrapper = mountStatus({});
    await wrapper.setProps({ provider: 'gemini', model: 'gemini-2.5-flash' });
    resolveGemini({
      ...baseStatus,
      provider: 'gemini',
      models: [{ provider: 'gemini', id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' }],
    });
    await flushPromises();
    resolveOpenAI(baseStatus);
    await flushPromises();

    expect(wrapper.text()).toContain('Gemini 2.5 Flash');
    expect(wrapper.text()).not.toContain('GPT-5 mini');

    wrapper.unmount();
    expect(() => resolveOpenAI(baseStatus)).not.toThrow();
  });
});
