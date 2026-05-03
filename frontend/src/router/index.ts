import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router';

import AppLayout from '@/layouts/AppLayout.vue';
import AuthLayout from '@/layouts/AuthLayout.vue';
import BookCreatePage from '@/pages/books/BookCreatePage.vue';
import BookDetailPage from '@/pages/books/BookDetailPage.vue';
import BookEditPage from '@/pages/books/BookEditPage.vue';
import BooksListPage from '@/pages/books/BooksListPage.vue';
import CategoriesPage from '@/pages/categories/CategoriesPage.vue';
import DashboardPage from '@/pages/dashboard/DashboardPage.vue';
import LocationsPage from '@/pages/locations/LocationsPage.vue';
import LoginPage from '@/pages/login/LoginPage.vue';
import { useAuthStore } from '@/stores/auth';

function isAdminRoute(to: RouteLocationNormalized) {
  return to.matched.some((record) => record.meta.adminOnly);
}

function isProtectedRoute(to: RouteLocationNormalized) {
  return to.matched.some((record) => record.meta.requiresAuth);
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      component: AuthLayout,
      meta: { guestOnly: true },
      children: [
        {
          path: '',
          name: 'login',
          component: LoginPage,
        },
      ],
    },
    {
      path: '/',
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'dashboard',
          component: DashboardPage,
          meta: { title: '首页' },
        },
        {
          path: 'books',
          name: 'books',
          component: BooksListPage,
          meta: { title: '藏书' },
        },
        {
          path: 'books/new',
          name: 'book-new',
          component: BookCreatePage,
          meta: { title: '新增图书' },
        },
        {
          path: 'books/:id',
          name: 'book-detail',
          component: BookDetailPage,
          meta: { title: '图书详情' },
        },
        {
          path: 'books/:id/edit',
          name: 'book-edit',
          component: BookEditPage,
          meta: { title: '编辑图书' },
        },
        {
          path: 'categories',
          name: 'categories',
          component: CategoriesPage,
          meta: { title: '分类管理', requiresAuth: true, adminOnly: true },
        },
        {
          path: 'locations',
          name: 'locations',
          component: LocationsPage,
          meta: { title: '位置管理', requiresAuth: true, adminOnly: true },
        },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const authStore = useAuthStore();

  if (authStore.token && !authStore.currentUser && !authStore.isFetchingMe) {
    try {
      await authStore.fetchMe();
    } catch {
      authStore.clearSession();
    }
  }

  if (to.meta.guestOnly && authStore.isAuthenticated) {
    return { name: 'dashboard' };
  }

  if (isProtectedRoute(to) && !authStore.isAuthenticated) {
    return {
      name: 'login',
      query: {
        redirect: to.fullPath,
      },
    };
  }

  if (isAdminRoute(to) && !authStore.isAdmin) {
    return { name: 'dashboard' };
  }

  return true;
});

export default router;
