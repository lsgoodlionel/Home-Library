import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SystemAIConfig } from '@/types/settings';
import ServerAISettingsPanel from './ServerAISettingsPanel.vue';

const mocks = vi.hoisted(() => ({
  fetchSystemAIConfig: vi.fn(),
  saveSystemAIConfig: vi.fn(),
  resetSystemAIConfig: vi.fn(),
  testSystemAIConfig: vi.fn(),
}));

vi.mock('@/api/settings', () => ({
  fetchSystemAIConfig: mocks.fetchSystemAIConfig,
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

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchSystemAIConfig.mockResolvedValue(config);
  mocks.saveSystemAIConfig.mockResolvedValue({ ...config, configurationSource: 'database', configVersion: 8 });
  mocks.resetSystemAIConfig.mockResolvedValue(config);
  mocks.testSystemAIConfig.mockResolvedValue(healthy);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ServerAISettingsPanel', () => {
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
    expect(wrapper.text()).toContain(config.defaultBaseUrl);
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

  it('clears every sensitive ref after success failure and dialog close', async () => {
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
    expect((input(wrapper, 'access-client-id').element as HTMLInputElement).value).toBe('');
    expect((input(wrapper, 'access-client-secret').element as HTMLInputElement).value).toBe('');

    await input(wrapper, 'access-client-id').setValue('success-client');
    await input(wrapper, 'access-client-secret').setValue('success-secret');
    await openSaveAuth(wrapper);
    await fillAuth(wrapper);
    await button(wrapper, '确认保存').trigger('click');
    await flushPromises();
    expect((input(wrapper, 'access-client-id').element as HTMLInputElement).value).toBe('');
    expect((input(wrapper, 'access-client-secret').element as HTMLInputElement).value).toBe('');

    await input(wrapper, 'access-client-id').setValue('closed-client');
    await input(wrapper, 'access-client-secret').setValue('closed-secret');
    await openSaveAuth(wrapper);
    await fillAuth(wrapper);
    await button(wrapper, '取消').trigger('click');
    await flushPromises();
    expect((input(wrapper, 'access-client-id').element as HTMLInputElement).value).toBe('');
    expect((input(wrapper, 'access-client-secret').element as HTMLInputElement).value).toBe('');
    expect(wrapper.find('.el-dialog').isVisible()).toBe(false);
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
