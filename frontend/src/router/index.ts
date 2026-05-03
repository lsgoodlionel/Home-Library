import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router';

import AppLayout from '@/layouts/AppLayout.vue';
import AuthLayout from '@/layouts/AuthLayout.vue';
import DashboardPage from '@/pages/dashboard/DashboardPage.vue';
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
