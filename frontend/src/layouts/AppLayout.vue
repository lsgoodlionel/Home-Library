<script setup lang="ts">
import {
  Collection,
  DataAnalysis,
  HomeFilled,
  Location,
  Notebook,
  Reading,
  Search,
  Setting,
  User,
} from '@element-plus/icons-vue';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAuthStore } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const activeMenu = computed(() => route.path);

const navItems = [
  { label: '首页', path: '/', icon: HomeFilled },
  { label: '藏书', path: '/books', icon: Collection },
  { label: '智能入库', path: '/smart-import', icon: Search },
  { label: '借阅', path: '/borrow', icon: Reading },
  { label: '阅读笔记', path: '/reading', icon: Notebook },
  { label: '统计', path: '/stats', icon: DataAnalysis },
  { label: '分类', path: '/categories', icon: Collection, adminOnly: true },
  { label: '位置', path: '/locations', icon: Location, adminOnly: true },
  { label: '用户', path: '/users', icon: User, adminOnly: true },
  { label: '设置', path: '/settings', icon: Setting, adminOnly: true },
];

const visibleNavItems = computed(() =>
  navItems.filter((item) => !item.adminOnly || authStore.isAdmin),
);

async function handleLogout() {
  await authStore.logout();
  await router.push({ name: 'login' });
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside class="app-sidebar" width="232px">
      <div class="brand">
        <div class="brand-mark">HL</div>
        <div>
          <div class="brand-title">Home Library</div>
          <div class="brand-subtitle">家藏书库</div>
        </div>
      </div>

      <el-menu :default-active="activeMenu" router class="side-menu">
        <el-menu-item v-for="item in visibleNavItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div>
          <div class="page-title">{{ route.meta.title || 'Home Library' }}</div>
          <div class="page-subtitle">家庭藏书管理系统</div>
        </div>

        <div class="header-actions">
          <span class="user-name">{{ authStore.currentUser?.displayName || '未命名用户' }}</span>
          <el-button plain @click="handleLogout">退出</el-button>
        </div>
      </el-header>

      <el-main class="app-main">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>
