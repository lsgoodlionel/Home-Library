<script setup lang="ts">
import { Check, Close } from '@element-plus/icons-vue';

import type { AIStatus } from '@/types/ai';

const props = defineProps<{
  title: string;
  status: AIStatus;
  errorMessage?: string;
}>();

const emit = defineEmits<{
  accept: [];
  dismiss: [];
  retry: [];
}>();
</script>

<template>
  <div class="ai-recommendation-card">
    <div class="card-header">
      <div class="card-title">
        <el-icon class="ai-icon" color="var(--el-color-primary)">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 14H11v-2h2zm0-4H11V7h2z" />
          </svg>
        </el-icon>
        {{ title }}
      </div>
      <el-tag v-if="status === 'unavailable'" size="small" type="warning">Ollama 不可用</el-tag>
    </div>

    <div v-if="status === 'loading'" class="card-body loading-body">
      <el-skeleton :rows="2" animated />
    </div>

    <div v-else-if="status === 'error'" class="card-body error-body">
      <el-alert
        :closable="false"
        :description="errorMessage || 'AI 服务请求失败'"
        show-icon
        title="推荐失败"
        type="error"
      />
      <el-button size="small" @click="emit('retry')">重试</el-button>
    </div>

    <div v-else-if="status === 'unavailable'" class="card-body unavailable-body">
      <p>Ollama 服务当前不可用，无法获取 AI 推荐。您可以手动填写分类和标签。</p>
    </div>

    <div v-else-if="status === 'success'" class="card-body success-body">
      <slot />
      <div class="card-actions">
        <el-button :icon="Check" size="small" type="primary" @click="emit('accept')">采用</el-button>
        <el-button :icon="Close" plain size="small" @click="emit('dismiss')">忽略</el-button>
      </div>
    </div>

    <div v-else class="card-body idle-body">
      <slot name="idle" />
    </div>
  </div>
</template>

<style scoped>
.ai-recommendation-card {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
  background: var(--el-bg-color);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--el-fill-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ai-icon {
  font-size: 14px;
}

.card-body {
  padding: 14px;
}

.loading-body,
.error-body,
.unavailable-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.unavailable-body p {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.success-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.card-actions {
  display: flex;
  gap: 8px;
}

.idle-body {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}
</style>
