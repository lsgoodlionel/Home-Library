import { expect, test, type Page, type Route } from '@playwright/test';

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

  const settings = () => ({
    ai_enabled: aiEnabled,
    active_provider: activeProvider,
    default_model: providers.find((item) => item.provider === activeProvider)?.default_model || '',
    providers,
    ollama_runtime: {
      enabled: true,
      base_url: 'http://localhost:11434',
      default_model: 'qwen-test',
      connect_timeout_seconds: 20,
      read_timeout_seconds: 180,
      verify_tls: true,
      access_configured: false,
      uses_access: false,
    },
  });

  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
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
    if (path === '/api/system/ai-config') return json(route, {
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
    });
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
      operations.push(`${provider}:${action}`);
      return json(route, {
        provider,
        status: 'available',
        message: action === 'models' ? '模型列表获取成功' : action === 'generate-test' ? '生成测试成功' : '连接测试成功',
        checked_at: '2026-10-21T00:00:00Z',
        effective_model: provider === 'openai' ? 'gpt-mocked' : 'qwen-test',
        safe_base_url: provider === 'openai' ? 'https://api.openai.com' : 'http://localhost:11434',
        credential_state: provider === 'ollama' ? 'missing' : 'configured',
        models: action === 'models' ? [{ provider, id: 'gpt-mocked', name: 'GPT Mocked' }] : [],
        details: {},
      });
    }
    if (path === '/api/ai/health') return json(route, {
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
    if (path === '/api/books') return json(route, { items: [], total: 0, page: 1, page_size: 20 });
    return json(route, {});
  });

  return { operations, settings };
}

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('用户名').fill('admin');
  await page.getByLabel('密码').fill('synthetic-login-password');
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL('/');
}

test('configures cloud provider, switches AI off/on, and restores Ollama', async ({ page }) => {
  const api = await installApi(page);
  await login(page);
  await page.getByRole('menuitem', { name: '设置', exact: true }).click();

  await expect(page.getByRole('region', { name: '服务器 AI 配置' })).toBeVisible();
  const account = page.getByRole('region', { name: '当前账号 AI 配置' });
  const ollama = account.locator('[data-provider="ollama"]');
  const openai = account.locator('[data-provider="openai"]');
  await expect(ollama).toBeVisible();
  await expect(openai).toBeVisible();

  await openai.getByTestId('provider-enabled').click();
  await openai.getByTestId('provider-api-key').fill('synthetic-browser-key');
  await openai.getByRole('button', { name: '测试连接' }).click();
  await expect(openai.getByText('连接测试成功', { exact: true })).toBeVisible();
  await openai.getByRole('button', { name: '刷新模型' }).click();
  await expect(page.getByText('模型列表已刷新', { exact: true })).toBeVisible();
  await openai.getByTestId('provider-model').click();
  await page.getByRole('option', { name: 'GPT Mocked' }).click();
  await openai.getByRole('button', { name: '生成测试' }).click();
  await page.getByRole('button', { name: '继续生成测试' }).click();
  await expect(openai.getByText('生成测试成功', { exact: true })).toBeVisible();

  await account.getByRole('button', { name: '保存账号 AI 配置' }).click();
  await expect(page.getByText('当前账号 AI 配置已保存', { exact: true })).toBeVisible();
  await account.getByTestId('active-provider').click();
  await page.getByRole('option', { name: 'OpenAI' }).click();
  await account.getByRole('button', { name: '保存账号 AI 配置' }).click();
  await expect(account.getByTestId('active-provider')).toContainText('OpenAI');

  await account.getByTestId('account-ai-enabled').click();
  await account.getByRole('button', { name: '保存账号 AI 配置' }).click();
  expect(api.settings().ai_enabled).toBe(false);
  await page.reload();
  await expect(account.getByTestId('account-ai-enabled')).toHaveAttribute('aria-checked', 'false');

  await account.getByTestId('account-ai-enabled').click();
  await ollama.getByTestId('provider-enabled').click();
  await account.getByTestId('active-provider').click();
  await page.getByRole('option', { name: 'Ollama' }).click();
  await account.getByRole('button', { name: '保存账号 AI 配置' }).click();
  await expect(account.getByTestId('active-provider')).toContainText('Ollama');
  expect(api.settings().ai_enabled).toBe(true);
  expect(api.settings().active_provider).toBe('ollama');
  expect(api.operations).toEqual(['openai:test', 'openai:models', 'openai:generate-test']);

  await page.getByRole('menuitem', { name: '藏书', exact: true }).click();
  await expect(page).toHaveURL('/books');
  await expect(page.getByRole('heading', { name: '藏书' })).toBeVisible();
});
