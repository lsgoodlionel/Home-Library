import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import type { OllamaHealthStatus } from '@/types/ai';
import OllamaConnectionStatus from './OllamaConnectionStatus.vue';

const status: OllamaHealthStatus = {
  status: 'healthy',
  message: 'AI 服务连接正常',
  checkedAt: '2026-10-20T08:00:00Z',
  version: '0.12.6',
  installedModelCount: 3,
  runningModelCount: 1,
  generated: false,
  ollamaRuntime: {
    enabled: true,
    baseUrl: 'https://openclaw.lsgood.cn',
    defaultModel: 'qwen3.5:4b',
    connectTimeoutSeconds: 20,
    readTimeoutSeconds: 180,
    verifyTls: true,
    accessConfigured: true,
    usesAccess: true,
  },
};

function mountStatus(overrides: Partial<OllamaHealthStatus> = {}, isAdmin = false) {
  return mount(OllamaConnectionStatus, {
    props: {
      status: { ...status, ...overrides },
      isAdmin,
      loading: false,
    },
    global: {
      stubs: {
        ElAlert: { template: '<div class="alert">{{ title }}<slot /></div>', props: ['title'] },
        ElButton: {
          template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
          props: ['disabled', 'loading'],
          emits: ['click'],
        },
        ElDescriptions: { template: '<dl><slot /></dl>' },
        ElDescriptionsItem: { template: '<div><dt>{{ label }}</dt><dd><slot /></dd></div>', props: ['label'] },
        ElTag: { template: '<span><slot /></span>' },
      },
    },
  });
}

describe('OllamaConnectionStatus', () => {
  it('shows_access_credentials_as_configured_status_only', () => {
    const wrapper = mountStatus();

    expect(wrapper.text()).toContain('Access 凭据');
    expect(wrapper.text()).toContain('已配置');
    expect(wrapper.text()).not.toContain('Client ID');
    expect(wrapper.text()).not.toContain('Client Secret');
  });

  it('warns_when_current_url_does_not_use_access', () => {
    const wrapper = mountStatus({
      ollamaRuntime: { ...status.ollamaRuntime!, usesAccess: false },
    });

    expect(wrapper.text()).toContain('此地址不会携带服务器 Cloudflare Access 凭据');
  });

  it('hides_admin_test_actions_for_members', () => {
    const wrapper = mountStatus({}, false);

    expect(wrapper.findAll('button')).toHaveLength(0);
  });

  it('emits_separate_check_test_and_generate_actions_for_admin', async () => {
    const wrapper = mountStatus({}, true);
    const buttons = wrapper.findAll('button');

    expect(buttons.map((button) => button.text())).toEqual(['检查连接', '普通测试', '生成测试']);
    await buttons[0].trigger('click');
    await buttons[1].trigger('click');
    await buttons[2].trigger('click');

    expect(wrapper.emitted('check')).toHaveLength(1);
    expect(wrapper.emitted('test')).toHaveLength(1);
    expect(wrapper.emitted('test-generate')).toHaveLength(1);
  });
});
