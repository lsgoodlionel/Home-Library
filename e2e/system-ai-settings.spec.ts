import { expect, test, type Page, type Route } from '@playwright/test';

// Disable failure DOM snapshots, which could contain entered secrets.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = '1';

test.use({ trace: 'off', video: 'off', screenshot: 'off' });

const adminUser = {
  id: 1,
  username: 'admin',
  display_name: '管理员',
  role: 'admin',
  status: 'active',
};

const environmentConfig = {
  enabled: true,
  default_base_url: 'https://ollama.test.example',
  trusted_base_url: 'https://ollama.test.example',
  default_model: 'test-model:latest',
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

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installControlledApi(page: Page, role: 'admin' | 'member' = 'admin') {
  const user = { ...adminUser, username: role, role };
  const serverRequests: string[] = [];
  const interceptedPaths: string[] = [];
  const routeApi = async (pathname: string, handler: (route: Route) => unknown) => {
    await page.route((url) => url.pathname === pathname, async (route) => {
      interceptedPaths.push(new URL(route.request().url()).pathname);
      if (pathname.startsWith('/api/system/')) serverRequests.push(route.request().method());
      await handler(route);
    });
  };
  let systemConfig = structuredClone(environmentConfig);
  let forcedHealthFailure = false;
  let saveRequests = 0;
  let resetRequests = 0;
  let submittedBothAccessValues = false;

  const runtime = () => ({
    enabled: systemConfig.enabled,
    base_url: systemConfig.default_base_url,
    default_model: systemConfig.default_model,
    connect_timeout_seconds: systemConfig.connect_timeout_seconds,
    read_timeout_seconds: systemConfig.read_timeout_seconds,
    verify_tls: systemConfig.verify_tls,
    access_configured: systemConfig.credential_state.credentials_usable,
    uses_access: systemConfig.credential_state.credentials_usable,
  });
  const accountConfig = () => ({
    active_provider: 'ollama',
    default_model: systemConfig.default_model,
    providers: [{
      provider: 'ollama',
      enabled: true,
      base_url: systemConfig.default_base_url,
      api_key: '',
      default_model: systemConfig.default_model,
      note: '受服务器边界约束的当前账号 Ollama 偏好',
      has_api_key: false,
    }],
    ollama_runtime: runtime(),
  });
  const healthy = () => ({
    status: 'healthy',
    message: '测试上游连接正常',
    checked_at: '2026-10-20T08:00:00Z',
    version: 'test-upstream',
    installed_model_count: 1,
    running_model_count: 0,
    generated: false,
    ollama_runtime: runtime(),
  });

  await routeApi('/api/auth/login', (route) => json(route, {
    access_token: 'synthetic-admin-token',
    token_type: 'bearer',
    expires_in: 3600,
    user,
  }));
  await routeApi('/api/auth/me', (route) => json(route, user));
  await routeApi('/api/stats/overview', (route) => json(route, {
    total_books: 0, available_books: 0, borrowed_books: 0, read_books: 0,
    unread_books: 0, favorite_books: 0, recent_books: [], active_borrows: [],
  }));
  await routeApi('/api/version', (route) => json(route, {
    app_name: 'Home Library',
    version: 'e2e',
    environment: 'isolated',
  }));
  await routeApi('/api/search/config', (route) => json(route, { providers: [] }));
  await routeApi('/api/ai/config', (route) => json(route, accountConfig()));
  await routeApi('/api/system/ai-config/test', (route) => {
    if (forcedHealthFailure) {
      return json(route, { error: { code: 'AI_CONNECT_TIMEOUT', message: 'controlled upstream unavailable' } }, 503);
    }
    return json(route, healthy());
  });
  await routeApi('/api/system/ai-config', async (route) => {
    if (route.request().method() === 'PUT') {
      saveRequests += 1;
      const body = route.request().postDataJSON() as Record<string, unknown>;
      submittedBothAccessValues = Boolean(body.access_client_id) && Boolean(body.access_client_secret);
      systemConfig = {
        ...systemConfig,
        enabled: Boolean(body.enabled),
        default_base_url: String(body.default_base_url),
        trusted_base_url: String(body.trusted_base_url),
        default_model: String(body.default_model),
        connect_timeout_seconds: Number(body.connect_timeout_seconds),
        read_timeout_seconds: Number(body.read_timeout_seconds),
        verify_tls: Boolean(body.verify_tls),
        credential_state: {
          access_client_id_configured: submittedBothAccessValues,
          access_client_secret_configured: submittedBothAccessValues,
          credentials_usable: submittedBothAccessValues,
          source: 'database',
        },
        configuration_source: 'database',
        config_version: 1,
      };
      forcedHealthFailure = true;
      return json(route, systemConfig);
    }
    if (route.request().method() === 'DELETE') {
      resetRequests += 1;
      systemConfig = structuredClone(environmentConfig);
      forcedHealthFailure = false;
      return json(route, systemConfig);
    }
    return json(route, systemConfig);
  });
  await routeApi('/api/ai/health', (route) => {
    if (forcedHealthFailure) {
      return json(route, { error: { code: 'AI_CONNECT_TIMEOUT', message: 'controlled upstream unavailable' } }, 503);
    }
    return json(route, healthy());
  });
  await routeApi('/api/books', (route) => json(route, {
    items: [], total: 0, page: 1, page_size: 20,
  }));
  await routeApi('/api/categories', (route) => json(route, []));
  await routeApi('/api/locations', (route) => json(route, []));

  return {
    serverRequests,
    interceptedPaths,
    get saveRequests() { return saveRequests; },
    get resetRequests() { return resetRequests; },
    get submittedBothAccessValues() { return submittedBothAccessValues; },
  };
}

async function loginAsAdmin(page: Page, username = 'admin') {
  await page.goto('/login');
  await page.getByLabel('用户名').fill(username);
  await page.getByLabel('密码').fill('synthetic-login-password');
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page).toHaveURL('/');
}

test.describe('system AI settings', () => {
  test('API mocks preserve Vite source modules and mount login', async ({ page }) => {
    const api = await installControlledApi(page);
    await page.goto('/login');
    await expect(page.getByLabel('用户名')).toBeVisible();
    const module = await page.evaluate(async () => {
      const response = await fetch('/src/api/books.ts');
      return { type: response.headers.get('content-type'), body: await response.text() };
    });
    expect(module.type).toContain('javascript');
    expect(module.body).toContain('getBooks');
    expect(api.interceptedPaths.some((path) => path.startsWith('/src/'))).toBe(false);
  });

  test('member reaches account preferences through real sidebar and router without server access', async ({ page }) => {
    const api = await installControlledApi(page, 'member');
    await loginAsAdmin(page, 'member');
    await expect(page.getByRole('menuitem', { name: '设置' })).toBeVisible();
    await page.getByRole('menuitem', { name: '设置' }).click();
    await expect(page).toHaveURL('/settings');
    await expect(page.getByRole('heading', { name: '当前账号 AI 偏好' })).toBeVisible();
    await expect(page.getByRole('region', { name: '服务器 AI 配置' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '保存服务器配置' })).toHaveCount(0);
    await page.reload();
    await expect(page).toHaveURL('/settings');
    await expect(page.getByRole('heading', { name: '当前账号 AI 偏好' })).toBeVisible();
    expect(api.serverRequests).toEqual([]);
    for (const path of ['/users', '/categories', '/locations']) {
      await page.goto(path);
      await expect(page).toHaveURL('/');
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: '当前账号 AI 偏好' })).toBeVisible();
    await expect(page.getByRole('button', { name: '保存设置', exact: true })).toBeVisible();
    expect(api.serverRequests).toEqual([]);
  });

  test('admin saves, reloads and resets server AI settings while failures stay isolated', async ({ page }) => {
    const api = await installControlledApi(page);
    await loginAsAdmin(page);
    await page.getByRole('menuitem', { name: '设置', exact: true }).click();
    await expect(page).toHaveURL('/settings');

    const server = page.getByRole('region', { name: '服务器 AI 配置' });
    await expect(server).toBeVisible();
    await expect(page.getByRole('heading', { name: '当前运行状态' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '当前账号 AI 偏好' })).toBeVisible();

    await expect(server.getByTestId('access-client-id')).toHaveJSProperty('tagName', 'INPUT');
    await server.getByTestId('access-client-id').fill('synthetic-client-id');
    await server.getByRole('button', { name: '保存服务器配置' }).click();
    await expect(page.getByText('必须同时填写完整的 Access Client ID 和 Client Secret', { exact: true })).toBeVisible();
    expect(api.saveRequests).toBe(0);

    await server.getByTestId('access-client-secret').fill('synthetic-client-secret');
    await server.getByPlaceholder('qwen3.5:4b').fill('persisted-test-model');
    await server.getByRole('button', { name: '保存服务器配置' }).click();

    const authDialog = page.getByTestId('auth-dialog');
    await expect(authDialog).toBeVisible();
    await expect(authDialog.getByLabel('当前管理员密码')).toBeVisible();
    await expect(authDialog.getByLabel('服务器升级专用密码')).toBeVisible();
    await authDialog.getByLabel('当前管理员密码').fill('synthetic-admin-password');
    await authDialog.getByLabel('服务器升级专用密码').fill('synthetic-upgrade-password');
    await authDialog.getByRole('button', { name: '确认保存' }).click();

    await expect(page.getByText('服务器 AI 配置已保存', { exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Ollama 连接状态' }).getByText('连接异常', { exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Ollama 连接状态' }).getByText('连接 AI 服务超时，请检查服务地址和网络连接。', { exact: true })).toBeVisible();
    await expect(authDialog).toBeHidden();
    expect(api.saveRequests).toBe(1);
    expect(api.submittedBothAccessValues).toBe(true);

    await page.reload();
    await expect(server.locator('.el-tag').getByText('数据库配置', { exact: true })).toBeVisible();
    await expect(server.getByPlaceholder('qwen3.5:4b')).toHaveValue('persisted-test-model');
    await expect(server.getByText('凭据完整且可用', { exact: true })).toBeVisible();
    await expect(page.locator('.el-card__header').getByText('外部检索', { exact: true })).toBeVisible();

    // AI is still failing here: ordinary book navigation must remain usable.
    await page.getByRole('menuitem', { name: '藏书', exact: true }).click();
    await expect(page).toHaveURL('/books');
    await expect(page.getByRole('heading', { name: '藏书' })).toBeVisible();
    await expect(page.getByText('暂无符合条件的图书', { exact: true })).toBeVisible();
    await page.getByRole('menuitem', { name: '设置', exact: true }).click();
    await expect(page).toHaveURL('/settings');
    await expect(page.getByRole('region', { name: 'Ollama 连接状态' }).getByText('连接异常', { exact: true })).toBeVisible();

    await server.getByRole('button', { name: '恢复环境变量配置' }).click();
    await page.getByRole('button', { name: '继续恢复' }).click();
    await expect(authDialog).toBeVisible();
    await authDialog.getByLabel('当前管理员密码').fill('synthetic-admin-password');
    await authDialog.getByLabel('服务器升级专用密码').fill('synthetic-upgrade-password');
    await authDialog.getByRole('button', { name: '确认恢复' }).click();

    await expect(page.getByText('服务器 AI 配置已恢复', { exact: true })).toBeVisible();
    await expect(server.locator('.el-tag').getByText('环境变量', { exact: true })).toBeVisible();
    expect(api.resetRequests).toBe(1);

    await page.getByRole('menuitem', { name: '藏书', exact: true }).click();
    await expect(page).toHaveURL('/books');
    await expect(page.getByRole('heading', { name: '藏书' })).toBeVisible();
    await expect(page.getByText('暂无符合条件的图书', { exact: true })).toBeVisible();
  });

  test('server AI sections remain operable without horizontal overflow on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installControlledApi(page);
    await loginAsAdmin(page);
    await page.goto('/settings');

    const server = page.getByRole('region', { name: '服务器 AI 配置' });
    await expect(server).toBeVisible();
    await expect(server.getByRole('button', { name: '保存服务器配置' })).toBeVisible();
    await expect(server.getByRole('button', { name: '测试连接' })).toBeVisible();
    await expect(server.getByRole('button', { name: '恢复环境变量配置' })).toBeVisible();

    const layout = await page.evaluate(() => ({
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      serverRight: document.querySelector('[aria-label="服务器 AI 配置"]')?.getBoundingClientRect().right ?? 0,
    }));
    expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
    expect(layout.serverRight).toBeLessThanOrEqual(layout.viewportWidth);
  });
});
