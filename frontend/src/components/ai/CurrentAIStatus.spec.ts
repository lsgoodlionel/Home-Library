import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import * as aiApi from '@/api/ai';
import type { AIHealthStatus } from '@/types/ai';
import CurrentAIStatus from './CurrentAIStatus.vue';

const baseStatus: AIHealthStatus = {
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
    let resolveOpenAI!: (value: AIHealthStatus) => void;
    let resolveGemini!: (value: AIHealthStatus) => void;
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
