import { expect, test, type Locator, type Page, type Route } from '@playwright/test';

process.env.PLAYWRIGHT_NO_COPY_PROMPT = '1';
test.use({ trace: 'off', video: 'off', screenshot: 'off' });

const user = {
  id: 11,
  username: 'admin',
  display_name: '管理员',
  role: 'admin',
  status: 'active',
};

const providerDefaults = [
  ['ollama', true, 'http://localhost:11434', 'qwen-test', false],
  ['openai', false, 'https://api.openai.com/v1', 'gpt-test', false],
  ['deepseek', false, 'https://api.deepseek.com/v1', 'deepseek-test', false],
  ['moonshot', false, 'https://api.moonshot.cn/v1', 'kimi-test', false],
  ['qwen', false, 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-cloud-test', false],
  ['gemini', false, 'https://generativelanguage.googleapis.com/v1beta', 'gemini-test', false],
  ['custom', false, 'https://ai-gateway.example.test/v1', 'custom-test', false],
] as const;

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installApi(page: Page) {
  let aiEnabled = true;
  let activeProvider = 'ollama';
  let providers = providerDefaults.map(([provider, enabled, baseUrl, defaultModel, hasApiKey]) => ({
    provider,
    enabled,
    base_url: baseUrl,
    default_model: defaultModel,
    note: `${provider} deterministic mock`,
    has_api_key: hasApiKey,
    credential_state: hasApiKey ? 'configured' : 'missing',
  }));
  const operations: string[] = [];
  const drafts: Array<{ action: string; model: string; baseUrl: string; hasKey: boolean }> = [];
  const statusRequests: string[] = [];
  const unhandledRequests: string[] = [];
  const blockedRequests: string[] = [];
  const serverSaves: boolean[] = [];
  const serverConfig = {
    enabled: true,
    default_base_url: 'http://localhost:11434',
    trusted_base_url: 'https://ollama.example.test',
    default_model: 'qwen-test',
    connect_timeout_seconds: 20,
    read_timeout_seconds: 180,
    verify_tls: true,
    credential_state: {
      access_client_id_configured: false,
      access_client_secret_configured: false,
      credentials_usable: false,
      source: 'environment',
    },
    configuration_source: 'environment',
    config_version: 0,
  };

  const settings = () => ({
    ai_enabled: aiEnabled,
    active_provider: activeProvider,
    default_model: providers.find((item) => item.provider === activeProvider)?.default_model || '',
    providers,
    ollama_runtime: {
      enabled: serverConfig.enabled,
      base_url: 'http://localhost:11434',
      default_model: 'qwen-test',
      connect_timeout_seconds: 20,
      read_timeout_seconds: 180,
      verify_tls: true,
      access_configured: false,
      uses_access: false,
    },
  });

  const mockOrigin = new URL(process.env.E2E_BASE_URL || 'http://127.0.0.1:5173').origin;
  await page.route('**/*', async (route) => {
    if (new URL(route.request().url()).origin !== mockOrigin) {
      blockedRequests.push('external');
      return route.abort();
    }
    return route.continue();
  });
  await page.route((url) => url.origin === mockOrigin && url.pathname.startsWith('/api/'), async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/auth/login') return json(route, {
      access_token: 'synthetic-browser-token', token_type: 'bearer', expires_in: 3600, user,
    });
    if (path === '/api/auth/me') return json(route, user);
    if (path === '/api/stats/overview') return json(route, {
      total_books: 0, available_books: 0, borrowed_books: 0, read_books: 0,
      unread_books: 0, favorite_books: 0, recent_books: [], active_borrows: [],
    });
    if (path === '/api/version') return json(route, { app_name: 'Home Library', version: 'e2e', environment: 'test' });
    if (path === '/api/search/config') return json(route, { providers: [] });
    if (path === '/api/system/ai-config') {
      if (request.method() === 'PUT') {
        serverConfig.enabled = request.postDataJSON().enabled;
        serverConfig.configuration_source = 'database';
        serverConfig.config_version += 1;
        serverSaves.push(serverConfig.enabled);
      }
      return json(route, serverConfig);
    }
    if (path === '/api/system/ai-config/test') return json(route, serverConfig.enabled ? {
      status: 'healthy', message: 'Ollama 网关连接正常', checked_at: null,
      installed_model_count: 1, running_model_count: 0, generated: false,
      ollama_runtime: settings().ollama_runtime,
    } : { error: { code: 'AI_SERVICE_DISABLED', message: 'AI 服务尚未启用' } }, serverConfig.enabled ? 200 : 503);
    if (path === '/api/system/ai-config/models') return json(route, { models: [{ name: 'qwen-test' }] });
    if (path === '/api/ai/config' && request.method() === 'GET') return json(route, settings());
    if (path === '/api/ai/config' && request.method() === 'PUT') {
      const body = request.postDataJSON() as {
        ai_enabled: boolean;
        active_provider: string;
        providers: Array<Record<string, unknown>>;
      };
      aiEnabled = body.ai_enabled;
      activeProvider = body.active_provider;
      providers = body.providers.map((item) => {
        const previous = providers.find((candidate) => candidate.provider === item.provider);
        const hasApiKey = item.provider === 'ollama'
          ? false
          : Boolean(item.api_key) || Boolean(previous?.has_api_key);
        return {
          provider: String(item.provider),
          enabled: Boolean(item.enabled),
          base_url: String(item.base_url),
          default_model: String(item.default_model),
          note: String(item.note || ''),
          has_api_key: hasApiKey,
          credential_state: hasApiKey ? 'configured' : 'missing',
        };
      });
      return json(route, settings());
    }
    const operation = path.match(/^\/api\/ai\/providers\/([^/]+)\/(test|models|generate-test)$/);
    if (operation) {
      const [, provider, action] = operation;
      const config = providers.find((item) => item.provider === provider)!;
      if (request.method() !== 'POST' || !config) {
        unhandledRequests.push(`${request.method()} ${path}`);
        return json(route, { error: { code: 'UNMOCKED_OPERATION', message: '未定义的测试操作' } }, 405);
      }
      const draft = request.postDataJSON() as { provider?: string; base_url?: string; model?: string; api_key?: string };
      if (draft.provider) {
        if (draft.provider !== provider || !draft.base_url || !draft.model
          || (draft.api_key && draft.api_key !== 'synthetic-browser-key')
          || (provider !== 'ollama' && !config.has_api_key && !draft.api_key)) {
          unhandledRequests.push('invalid-provider-draft');
          return json(route, { error: { code: 'AI_CONFIG_INVALID', message: '测试草稿配置无效' } }, 422);
        }
        operations.push(`${provider}:${action}`);
        drafts.push({ action, model: draft.model, baseUrl: draft.base_url, hasKey: Boolean(draft.api_key) });
      } else statusRequests.push(`${provider}:${action}`);
      return json(route, {
        provider,
        status: 'available',
        message: action === 'models' ? '模型列表获取成功' : action === 'generate-test' ? '生成测试成功' : '连接测试成功',
        checked_at: '2026-10-21T00:00:00Z',
        effective_model: draft.model || config.default_model,
        safe_base_url: draft.base_url || config.base_url,
        credential_state: provider === 'ollama' ? 'missing' : 'configured',
        models: action === 'models' ? [{ provider, id: provider === 'openai' ? 'gpt-mocked' : 'qwen-test', name: provider === 'openai' ? 'GPT Mocked' : 'Qwen Mocked' }] : [],
        details: {},
      });
    }
    if (path === '/api/ai/health') {
      statusRequests.push(`${activeProvider}:health`);
      return json(route, {
      provider: activeProvider,
      status: aiEnabled ? 'available' : 'unavailable',
      message: aiEnabled ? '当前服务商可用' : '账号 AI 已停用',
      checked_at: null,
      effective_model: settings().default_model,
      safe_base_url: '',
      credential_state: activeProvider === 'ollama' ? 'missing' : 'configured',
      models: [],
      details: {},
      });
    }
    if (path === '/api/books') return json(route, { items: [], total: 0, page: 1, page_size: 20 });
    if (path === '/api/categories' || path === '/api/locations') return json(route, []);
    unhandledRequests.push(`${request.method()} ${path}`);
    return json(route, { error: { code: 'UNMOCKED_API', message: '未定义的测试接口' } }, 501);
  });

  return { operations, drafts, statusRequests, unhandledRequests, blockedRequests, serverSaves, settings };
}

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('用户名').fill('admin');
  await page.getByLabel('密码').fill('synthetic-login-password');
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL('/');
}

test('configures cloud provider, switches AI off/on, and restores Ollama', async ({ page }) => {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  page.on('pageerror', () => pageErrors.push('pageerror'));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const expectedDisabledProbe = message.location().url.endsWith('/api/system/ai-config/test')
      && /\b503\b/.test(message.text());
    if (!expectedDisabledProbe) consoleErrors.push('unexpected-console-error');
  });
  const api = await installApi(page);
  await login(page);
  await page.getByRole('menuitem', { name: '设置', exact: true }).click();

  const server = page.getByRole('region', { name: '服务器 Ollama 网关' });
  await expect(server).toBeVisible();
  const account = page.getByRole('region', { name: '当前账号 AI 配置' });
  const ollama = account.locator('[data-provider="ollama"]');
  const openai = account.locator('[data-provider="openai"]');
  const status = page.locator('.current-ai-status');
  await expect(account.locator('[data-provider]')).toHaveCount(7);
  await expect(ollama).toBeVisible();
  await expect(openai).toBeVisible();
  await expect(status).toContainText('Ollama');
  await expect(status).toContainText('连接正常');

  async function saveAccount() {
    const response = page.waitForResponse((response) =>
      new URL(response.url()).pathname === '/api/ai/config' && response.request().method() === 'PUT');
    const save = account.getByRole('button', { name: '保存账号 AI 配置' });
    await save.click();
    expect((await response).status()).toBe(200);
    await expect(save).toBeEnabled();
  }

  async function switchTo(provider: string) {
    await account.getByTestId('active-provider').locator('.el-select__wrapper').click();
    await page.getByRole('option', { name: provider, exact: true }).click();
    await saveAccount();
    await expect(status).toContainText(provider);
    await expect(status).toContainText('连接正常');
  }

  async function toggle(control: Locator, enabled: boolean) {
    await expect(control.getByRole('switch')).toHaveAttribute('aria-checked', String(!enabled));
    await control.click();
    await expect(control.getByRole('switch')).toHaveAttribute('aria-checked', String(enabled));
  }

  async function saveServer(enabled: boolean) {
    await toggle(server.getByTestId('enabled'), enabled);
    await server.getByRole('button', { name: '保存服务器配置' }).click();
    const dialog = page.getByTestId('auth-dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByLabel('当前管理员密码').fill('synthetic-admin-password');
    await dialog.getByLabel('服务器升级专用密码').fill('synthetic-upgrade-password');
    const saved = page.waitForResponse((response) =>
      new URL(response.url()).pathname === '/api/system/ai-config' && response.request().method() === 'PUT');
    await dialog.getByRole('button', { name: '确认保存' }).click();
    expect((await saved).status()).toBe(200);
    await expect(dialog).toBeHidden();
    await expect(server.getByTestId('enabled').getByRole('switch')).toHaveAttribute('aria-checked', String(enabled));
  }

  await toggle(openai.getByTestId('provider-enabled'), true);
  await openai.getByTestId('provider-address').fill('https://openai.example.test/v1');
  await openai.getByTestId('provider-api-key').fill('synthetic-browser-key');
  await openai.getByRole('button', { name: '测试连接' }).click();
  await expect(openai.getByText('连接测试成功', { exact: true })).toBeVisible();
  await openai.getByRole('button', { name: '刷新模型' }).click();
  await expect(page.getByText('模型列表已刷新', { exact: true })).toBeVisible();
  await openai.getByTestId('provider-model').locator('.el-select__wrapper').click();
  await page.getByRole('option', { name: 'GPT Mocked', exact: true }).click();
  await openai.getByRole('button', { name: '生成测试' }).click();
  await expect(page.getByRole('dialog', { name: '确认生成测试' })).toBeVisible();
  expect(api.operations).not.toContain('openai:generate-test');
  await page.getByRole('button', { name: '继续生成测试' }).click();
  await expect(openai.getByText('生成测试成功', { exact: true })).toBeVisible();

  await saveAccount();
  await expect(page.getByText('当前账号 AI 配置已保存', { exact: true })).toBeVisible();
  await expect(openai.getByTestId('provider-api-key')).toHaveValue('');
  await switchTo('OpenAI');
  await expect(account.getByTestId('active-provider')).toContainText('OpenAI');
  await expect(status).toContainText('gpt-mocked');

  // Cloud operations remain usable with both the Ollama entry and server gateway off.
  await toggle(ollama.getByTestId('provider-enabled'), false);
  await saveAccount();
  await saveServer(false);
  await expect(status).toContainText('OpenAI');
  await expect(status).toContainText('连接正常');
  await openai.getByRole('button', { name: '测试连接' }).click();
  await expect(openai.getByText('连接测试成功', { exact: true })).toBeVisible();
  expect(api.settings().providers.find((provider) => provider.provider === 'ollama')?.enabled).toBe(false);

  const beforeDisable = api.statusRequests.length;
  await toggle(account.getByTestId('account-ai-enabled'), false);
  await saveAccount();
  expect(api.settings().ai_enabled).toBe(false);
  await expect(status).toContainText('当前账号未启用 AI');
  await page.reload();
  await expect(account.getByTestId('account-ai-enabled').getByRole('switch')).toHaveAttribute('aria-checked', 'false');
  await expect(status).toContainText('当前账号未启用 AI');
  expect(api.statusRequests).toHaveLength(beforeDisable);

  await page.getByRole('menuitem', { name: '藏书', exact: true }).click();
  await expect(page).toHaveURL('/books');
  await expect(page.getByRole('heading', { name: '藏书', exact: true })).toBeVisible();
  await expect(page.getByText('暂无符合条件的图书', { exact: true })).toBeVisible();
  await page.getByRole('menuitem', { name: '设置', exact: true }).click();
  await expect(status).toContainText('当前账号未启用 AI');
  expect(api.statusRequests).toHaveLength(beforeDisable);

  await toggle(account.getByTestId('account-ai-enabled'), true);
  await saveAccount();
  await expect(status).toContainText('OpenAI');
  await expect(status).toContainText('连接正常');
  await saveServer(true);
  await toggle(ollama.getByTestId('provider-enabled'), true);
  await switchTo('Ollama');
  await page.reload();
  await expect(account.getByTestId('active-provider')).toContainText('Ollama');
  await expect(status).toContainText('Ollama');
  await expect(status).toContainText('连接正常');
  expect(api.settings().ai_enabled).toBe(true);
  expect(api.settings().active_provider).toBe('ollama');
  expect(api.operations).toEqual(['openai:test', 'openai:models', 'openai:generate-test', 'openai:test']);
  expect(api.drafts).toEqual([
    { action: 'test', model: 'gpt-test', baseUrl: 'https://openai.example.test/v1', hasKey: true },
    { action: 'models', model: 'gpt-test', baseUrl: 'https://openai.example.test/v1', hasKey: true },
    { action: 'generate-test', model: 'gpt-mocked', baseUrl: 'https://openai.example.test/v1', hasKey: true },
    { action: 'test', model: 'gpt-mocked', baseUrl: 'https://openai.example.test/v1', hasKey: false },
  ]);
  expect(api.serverSaves).toEqual([false, true]);
  expect(api.statusRequests).toContain('openai:health');
  expect(api.statusRequests).toContain('ollama:models');

  await page.getByRole('menuitem', { name: '藏书', exact: true }).click();
  await expect(page).toHaveURL('/books');
  await expect(page.getByRole('heading', { name: '藏书' })).toBeVisible();
  await expect(page.getByText('暂无符合条件的图书', { exact: true })).toBeVisible();
  expect(api.unhandledRequests).toEqual([]);
  expect(api.blockedRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
