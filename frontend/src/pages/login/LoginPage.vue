<script setup lang="ts">
import { Lock, User } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAuthStore } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const loading = ref(false);
const form = reactive({
  username: '',
  password: '',
});

async function handleLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码');
    return;
  }

  loading.value = true;

  try {
    await authStore.login({
      username: form.username,
      password: form.password,
    });

    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/';
    await router.push(redirect);
  } catch {
    ElMessage.error('登录失败，请检查账号或密码');
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-card">
    <h2>登录</h2>
    <p>进入家庭藏书管理工作台</p>

    <el-form label-position="top" @submit.prevent="handleLogin">
      <el-form-item label="用户名">
        <el-input v-model="form.username" autocomplete="username" size="large">
          <template #prefix>
            <el-icon><User /></el-icon>
          </template>
        </el-input>
      </el-form-item>

      <el-form-item label="密码">
        <el-input
          v-model="form.password"
          autocomplete="current-password"
          size="large"
          show-password
          type="password"
          @keyup.enter="handleLogin"
        >
          <template #prefix>
            <el-icon><Lock /></el-icon>
          </template>
        </el-input>
      </el-form-item>

      <el-button :loading="loading" class="login-button" native-type="submit" size="large" type="primary">
        登录
      </el-button>
    </el-form>
  </div>
</template>
