import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SystemAIConfig } from '@/types/settings';
import ServerAISettingsPanel from './ServerAISettingsPanel.vue';

const mocks = vi.hoisted(() => ({
  fetchSystemAIConfig: vi.fn(),
  fetchSystemAIModels: vi.fn(),
  saveSystemAIConfig: vi.fn(),
  resetSystemAIConfig: vi.fn(),
  testSystemAIConfig: vi.fn(),
}));

vi.mock('@/api/settings', () => ({
  fetchSystemAIConfig: mocks.fetchSystemAIConfig,
  fetchSystemAIModels: mocks.fetchSystemAIModels,
  saveSystemAIConfig: mocks.saveSystemAIConfig,
  resetSystemAIConfig: mocks.resetSystemAIConfig,
  testSystemAIConfig: mocks.testSystemAIConfig,
}));

const config: SystemAIConfig = {
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
};

const healthy = {
  status: 'healthy' as const,
  message: 'AI 服务连接正常',
  checkedAt: '2026-10-20T08:00:00Z',
  version: '0.12.6',
  installedModelCount: 3,
  runningModelCount: 1,
  generated: false,
  ollamaRuntime: null,
};

function button(wrapper: VueWrapper, label: string) {
  const found = wrapper.findAll('button').find((item) => item.text().includes(label));
  if (!found) throw new Error(`未找到按钮：${label}`);
  return found;
}

function input(wrapper: VueWrapper, testId: string) {
  const target = wrapper.get(`[data-testid="${testId}"]`);
  return target.element instanceof HTMLInputElement ? target : target.get('input');
}

async function mountPanel() {
  const wrapper = mount(ServerAISettingsPanel, { global: { plugins: [ElementPlus] } });
  await flushPromises();
  return wrapper;
}

async function openSaveAuth(wrapper: VueWrapper) {
  await button(wrapper, '保存服务器配置').trigger('click');
  await flushPromises();
}

async function fillAuth(wrapper: VueWrapper) {
  await input(wrapper, 'admin-password').setValue('current-admin-password');
  await input(wrapper, 'upgrade-password').setValue('server-upgrade-password');
}

function nonSensitiveFormState(wrapper: VueWrapper) {
  const urls = wrapper.findAll('input[placeholder="https://ollama.example.com"]');
  const timeouts = wrapper.findAll('input[role="spinbutton"]');
  return {
    enabled: wrapper.get('[data-testid="enabled"] input').attributes('aria-checked'),
    verifyTls: wrapper.get('[data-testid="verify-tls"] input').attributes('aria-checked'),
    defaultBaseUrl: (urls[0].element as HTMLInputElement).value,
    trustedBaseUrl: (urls[1].element as HTMLInputElement).value,
    defaultModel: (wrapper.get('[data-testid="server-default-model"] input').element as HTMLInputElement).value,
    connectTimeout: (timeouts[0].element as HTMLInputElement).value,
    readTimeout: (timeouts[1].element as HTMLInputElement).value,
  };
}

function expectAllSensitiveInputsEmpty(wrapper: VueWrapper) {
  expect((input(wrapper, 'access-client-id').element as HTMLInputElement).value).toBe('');
  expect((input(wrapper, 'access-client-secret').element as HTMLInputElement).value).toBe('');
  expect((input(wrapper, 'admin-password').element as HTMLInputElement).value).toBe('');
  expect((input(wrapper, 'upgrade-password').element as HTMLInputElement).value).toBe('');
}

async function closeAuthThroughDialog(wrapper: VueWrapper) {
  await wrapper.get('.el-dialog__headerbtn').trigger('click');
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchSystemAIConfig.mockResolvedValue(config);
  mocks.fetchSystemAIModels.mockResolvedValue([
    { name: 'qwen3.5:4b', size: '3.2 GB', modifiedAt: '2026-10-21T00:00:00Z' },
  ]);
  mocks.saveSystemAIConfig.mockResolvedValue({ ...config, configurationSource: 'database', configVersion: 8 });
  mocks.resetSystemAIConfig.mockResolvedValue(config);
  mocks.testSystemAIConfig.mockResolvedValue(healthy);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ServerAISettingsPanel', () => {
  it('uses the server Ollama gateway wording and explains trusted Origin without runtime summary duplication', async () => {
    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain('服务器 Ollama 网关');
    expect(wrapper.text()).toContain('默认 Ollama 服务地址');
    expect(wrapper.text()).toContain('允许携带 Access 凭据的可信 Origin');
    expect(wrapper.text()).toContain('该地址不是备用服务地址，只用于限制 Access 凭据发送目标');
    expect(wrapper.text()).not.toContain('连接超时20 秒');
    expect(wrapper.text()).not.toContain('读取超时180 秒');
  });

  it('rejects an Ollama API endpoint where a service root is required', async () => {
    const warning = vi.spyOn(ElMessage, 'warning');
    const wrapper = await mountPanel();
    const urls = wrapper.findAll('input[placeholder="https://ollama.example.com"]');
    await urls[0].setValue('https://openclaw.lsgood.cn/api/version');

    await button(wrapper, '保存服务器配置').trigger('click');
    await flushPromises();

    expect(warning).toHaveBeenCalledWith('Ollama 地址请填写服务根地址，不要包含 /api/version 等接口路径');
    expect(wrapper.find('.el-dialog').exists()).toBe(false);
  });

  it('loads server models and warns when the configured default is unavailable', async () => {
    const warning = vi.spyOn(ElMessage, 'warning');
    mocks.fetchSystemAIConfig.mockResolvedValueOnce({ ...config, defaultModel: 'missing-model' });
    mocks.fetchSystemAIModels.mockResolvedValueOnce([
      { name: 'remote-model', size: '2.1 GB', modifiedAt: '2026-10-21T00:00:00Z' },
    ]);
    const wrapper = await mountPanel();

    await button(wrapper, '刷新服务器模型').trigger('click');
    await flushPromises();

    expect(mocks.fetchSystemAIModels).toHaveBeenCalledTimes(1);
    expect(wrapper.findAllComponents({ name: 'ElOption' }).map((option) => option.props('label')))
      .toContain('remote-model');
    expect(warning).toHaveBeenCalledWith('当前默认模型不在服务器模型列表中，请重新选择');
  });

  it('renders source status and never renders saved credential values', async () => {
    const withUnexpectedSecrets = {
      ...config,
      credentialState: {
        ...config.credentialState,
        accessClientId: 'saved-client-must-not-render',
        accessClientSecret: 'saved-secret-must-not-render',
      },
    } as SystemAIConfig;
    mocks.fetchSystemAIConfig.mockResolvedValueOnce(withUnexpectedSecrets);

    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain('环境变量');
    expect(wrapper.text()).toContain('凭据完整且可用');
    expect((wrapper.findAll('input[placeholder="https://ollama.example.com"]')[0].element as HTMLInputElement).value)
      .toBe(config.defaultBaseUrl);
    expect(wrapper.text()).not.toContain('saved-client-must-not-render');
    expect(wrapper.text()).not.toContain('saved-secret-must-not-render');
    expect((input(wrapper, 'access-client-id').element as HTMLInputElement).value).toBe('');
    expect((input(wrapper, 'access-client-secret').element as HTMLInputElement).value).toBe('');
  });

  it('requires both passwords before server save', async () => {
    const warning = vi.spyOn(ElMessage, 'warning');
    const wrapper = await mountPanel();
    await openSaveAuth(wrapper);

    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();
    expect(warning).toHaveBeenCalledWith('请输入当前管理员密码和服务器升级专用密码');
    expect(mocks.saveSystemAIConfig).not.toHaveBeenCalled();

    await input(wrapper, 'admin-password').setValue('current-admin-password');
    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();
    expect(mocks.saveSystemAIConfig).not.toHaveBeenCalled();
  });

  it('preserves blank credentials and sends explicit clear only when selected', async () => {
    const warning = vi.spyOn(ElMessage, 'warning');
    const wrapper = await mountPanel();
    await openSaveAuth(wrapper);
    await fillAuth(wrapper);
    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();

    expect(mocks.saveSystemAIConfig).toHaveBeenNthCalledWith(1, expect.objectContaining({
      accessClientId: undefined,
      accessClientSecret: undefined,
      clearAccessCredentials: false,
    }));

    await wrapper.get('[data-testid="clear-access-credentials"] input').setValue(true);
    await openSaveAuth(wrapper);
    await fillAuth(wrapper);
    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();

    expect(mocks.saveSystemAIConfig).toHaveBeenNthCalledWith(2, expect.objectContaining({
      accessClientId: undefined,
      accessClientSecret: undefined,
      clearAccessCredentials: true,
    }));

    await input(wrapper, 'access-client-id').setValue('replacement-client');
    await openSaveAuth(wrapper);
    expect(warning).toHaveBeenCalledWith('必须同时填写完整的 Access Client ID 和 Client Secret');
    expect(mocks.saveSystemAIConfig).toHaveBeenCalledTimes(2);
  });

  it('requires an extra warning before disabling TLS verification', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm');
    confirm.mockRejectedValueOnce('cancel');
    const wrapper = await mountPanel();

    await wrapper.get('[data-testid="verify-tls"]').trigger('click');
    await openSaveAuth(wrapper);

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('关闭 TLS 证书验证'),
      'TLS 安全警告',
      expect.objectContaining({ type: 'warning' }),
    );
    expect(wrapper.find('.el-dialog').exists()).toBe(false);
    expect(mocks.saveSystemAIConfig).not.toHaveBeenCalled();

    confirm.mockResolvedValueOnce('confirm' as never);
    await openSaveAuth(wrapper);
    await fillAuth(wrapper);
    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();

    expect(mocks.saveSystemAIConfig).toHaveBeenCalledWith(expect.objectContaining({
      verifyTls: false,
      confirmInsecureTls: true,
    }));
  });

  it('clears all sensitive refs when TLS warning or reset pre-confirm is cancelled without changing config fields', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm');
    const wrapper = await mountPanel();

    await input(wrapper, 'access-client-id').setValue('pending-client');
    await input(wrapper, 'access-client-secret').setValue('pending-secret');
    await openSaveAuth(wrapper);
    await fillAuth(wrapper);
    await wrapper.get('[data-testid="verify-tls"]').trigger('click');
    const tlsFormState = nonSensitiveFormState(wrapper);
    confirm.mockRejectedValueOnce('cancel');

    await openSaveAuth(wrapper);

    expectAllSensitiveInputsEmpty(wrapper);
    expect(nonSensitiveFormState(wrapper)).toEqual(tlsFormState);

    await input(wrapper, 'access-client-id').setValue('reset-client');
    await input(wrapper, 'access-client-secret').setValue('reset-secret');
    await fillAuth(wrapper);
    const resetFormState = nonSensitiveFormState(wrapper);
    confirm.mockRejectedValueOnce('cancel');

    await button(wrapper, '恢复环境变量配置').trigger('click');
    await flushPromises();

    expectAllSensitiveInputsEmpty(wrapper);
    expect(nonSensitiveFormState(wrapper)).toEqual(resetFormState);
    expect(mocks.saveSystemAIConfig).not.toHaveBeenCalled();
    expect(mocks.resetSystemAIConfig).not.toHaveBeenCalled();
  });

  it('clears all four sensitive inputs through the actual el-dialog close hook before reopen', async () => {
    const wrapper = await mountPanel();

    await input(wrapper, 'access-client-id').setValue('closed-client');
    await input(wrapper, 'access-client-secret').setValue('closed-secret');
    await openSaveAuth(wrapper);
    await fillAuth(wrapper);

    await closeAuthThroughDialog(wrapper);
    await openSaveAuth(wrapper);

    expectAllSensitiveInputsEmpty(wrapper);
  });

  it('does not repopulate authentication inputs after save failure or success', async () => {
    const errorMessage = vi.spyOn(ElMessage, 'error');
    const wrapper = await mountPanel();
    mocks.saveSystemAIConfig.mockRejectedValueOnce({
      response: { data: { error: { message: '管理员密码错误' } } },
    });

    await input(wrapper, 'access-client-id').setValue('failed-client');
    await input(wrapper, 'access-client-secret').setValue('failed-secret');
    await openSaveAuth(wrapper);
    await fillAuth(wrapper);
    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();
    expect(errorMessage).toHaveBeenCalledWith('管理员密码错误');
    await openSaveAuth(wrapper);
    expectAllSensitiveInputsEmpty(wrapper);
    await closeAuthThroughDialog(wrapper);

    await input(wrapper, 'access-client-id').setValue('success-client');
    await input(wrapper, 'access-client-secret').setValue('success-secret');
    await openSaveAuth(wrapper);
    await fillAuth(wrapper);
    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();
    await openSaveAuth(wrapper);
    expectAllSensitiveInputsEmpty(wrapper);
  });

  it('uses a viewport-bounded authentication dialog width on narrow screens', async () => {
    const originalWidth = window.innerWidth;
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 320 });
    try {
      const wrapper = await mountPanel();
      await openSaveAuth(wrapper);

      const style = wrapper.get('.el-dialog').attributes('style');
      expect(style).toContain('--el-dialog-width: min(480px, calc(100vw - 32px))');
      expect(style).not.toContain('--el-dialog-width: 480px;');
    } finally {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: originalWidth });
    }
  });

  it('requires confirmation and both passwords before environment reset', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm');
    confirm.mockRejectedValueOnce('cancel');
    const wrapper = await mountPanel();

    await button(wrapper, '恢复环境变量配置').trigger('click');
    await flushPromises();
    expect(mocks.resetSystemAIConfig).not.toHaveBeenCalled();

    confirm.mockResolvedValueOnce('confirm' as never);
    await button(wrapper, '恢复环境变量配置').trigger('click');
    await flushPromises();
    await button(wrapper, '确认恢复').trigger('click');
    expect(mocks.resetSystemAIConfig).not.toHaveBeenCalled();

    mocks.testSystemAIConfig.mockRejectedValueOnce(new Error('upstream unavailable'));
    await fillAuth(wrapper);
    await button(wrapper, '确认恢复').trigger('click');
    await flushPromises();
    expect(mocks.resetSystemAIConfig).toHaveBeenCalledWith({
      adminPassword: 'current-admin-password',
      upgradePassword: 'server-upgrade-password',
    });
    expect(wrapper.emitted('runtime-changed')).toHaveLength(1);
    expect(JSON.stringify(wrapper.emitted('runtime-changed'))).not.toContain('password');
    expect(mocks.testSystemAIConfig).toHaveBeenCalledTimes(1);
  });

  it('emits runtime-changed after save even when follow-up health fails', async () => {
    mocks.testSystemAIConfig.mockRejectedValueOnce(new Error('upstream unavailable'));
    const warning = vi.spyOn(ElMessage, 'warning');
    const wrapper = await mountPanel();

    await input(wrapper, 'access-client-id').setValue('event-client-must-not-leak');
    await input(wrapper, 'access-client-secret').setValue('event-secret-must-not-leak');
    await openSaveAuth(wrapper);
    await fillAuth(wrapper);
    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();

    expect(mocks.saveSystemAIConfig).toHaveBeenCalledTimes(1);
    expect(mocks.testSystemAIConfig).toHaveBeenCalledTimes(1);
    expect(wrapper.emitted('runtime-changed')).toHaveLength(1);
    expect(JSON.stringify(wrapper.emitted('runtime-changed'))).not.toContain('must-not-leak');
    expect(warning).toHaveBeenCalledWith(expect.stringContaining('配置已保存，但连接测试失败'));
  });
});
