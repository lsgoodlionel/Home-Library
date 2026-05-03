import { expect, test } from '@playwright/test';

test.describe('Home Library smoke flows', () => {
  test('redirects protected book list access to login', async ({ page }) => {
    await page.goto('/books');

    await expect(page).toHaveURL(/\/login\?redirect=\/books$/);
    await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
  });

  test('login flow skeleton submits credentials and reaches dashboard', async ({ page }) => {
    await page.route('**/api/auth/login', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'test-token',
          token_type: 'bearer',
          expires_in: 86400,
          user: {
            id: 1,
            username: 'admin',
            display_name: '管理员',
            role: 'admin',
          },
        }),
      });
    });
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          username: 'admin',
          display_name: '管理员',
          role: 'admin',
          status: 'active',
        }),
      });
    });
    await page.route('**/api/stats/**', async (route) => {
      const url = route.request().url();
      const body = url.includes('/overview')
        ? {
            total_books: 0,
            available_books: 0,
            borrowed_books: 0,
            read_books: 0,
            unread_books: 0,
            favorite_books: 0,
            recent_books: [],
            active_borrows: [],
          }
        : url.includes('/reading')
          ? { unread: 0, reading: 0, read: 0, paused: 0 }
          : [];
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.goto('/login');
    await page.getByLabel('用户名').fill('admin');
    await page.getByLabel('密码').fill('change-me');
    await page.getByRole('button', { name: '登录' }).click();

    await expect(page).toHaveURL('/');
  });

  test('book list and create book flow skeleton render with mocked APIs', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('home_library_token', 'test-token');
    });
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          username: 'admin',
          display_name: '管理员',
          role: 'admin',
          status: 'active',
        }),
      });
    });
    await page.route('**/api/books?page=**', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
      });
    });
    await page.route('**/api/categories', async (route) => {
      await route.fulfill({ contentType: 'application/json', body: '[]' });
    });
    await page.route('**/api/locations', async (route) => {
      await route.fulfill({ contentType: 'application/json', body: '[]' });
    });

    await page.goto('/books');
    await expect(page).toHaveURL('/books');

    await page.goto('/books/new');
    await expect(page).toHaveURL('/books/new');
    await expect(page.getByLabel('书名')).toBeVisible();
  });
});
