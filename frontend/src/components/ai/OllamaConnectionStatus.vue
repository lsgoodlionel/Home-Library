<script setup lang="ts">
import { computed } from 'vue';

import type { OllamaHealthStatus } from '@/types/ai';

const props = defineProps<{
  status: OllamaHealthStatus | null;
  isAdmin: boolean;
  loading: boolean;
}>();

defineEmits<{
  check: [];
  test: [];
  'test-generate': [];
}>();

const runtime = computed(() => props.status?.ollamaRuntime || null);
const statusType = computed(() => {
  if (props.status?.status === 'healthy') return 'success';
  if (props.status?.status === 'error') return 'danger';
  return 'info';
});

function formatCheckedAt(value: string | null | undefined): string {
  if (!value) return '尚未检查';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '尚未检查' : date.toLocaleString('zh-CN', { hour12: false });
}
</script>

<template>
  <section class="ollama-status" aria-label="Ollama 连接状态">
    <div class="status-header">
      <div>
        <div class="status-title">Ollama 运行状态</div>
        <div class="status-message">{{ status?.message || '尚未检查' }}</div>
      </div>
      <el-tag :type="statusType">
        {{ status?.status === 'healthy' ? '连接正常' : status?.status === 'error' ? '连接异常' : '尚未检查' }}
      </el-tag>
    </div>

    <el-descriptions :column="2" border class="status-details">
      <el-descriptions-item label="服务器 AI">
        {{ runtime?.enabled ? '已启用' : '未启用' }}
      </el-descriptions-item>
      <el-descriptions-item label="TLS 验证">
        {{ runtime?.verifyTls ? '已启用' : '未启用' }}
      </el-descriptions-item>
      <el-descriptions-item label="有效地址">
        {{ runtime?.baseUrl || '未配置' }}
      </el-descriptions-item>
      <el-descriptions-item label="默认模型">
        {{ runtime?.defaultModel || '未配置' }}
      </el-descriptions-item>
      <el-descriptions-item label="连接超时">
        {{ runtime ? `${runtime.connectTimeoutSeconds} 秒` : '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="读取超时">
        {{ runtime ? `${runtime.readTimeoutSeconds} 秒` : '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="Access 凭据">
        {{ runtime?.accessConfigured ? '已配置' : '未配置' }}
      </el-descriptions-item>
      <el-descriptions-item label="当前使用 Access">
        {{ runtime?.usesAccess ? '是' : '否' }}
      </el-descriptions-item>
      <el-descriptions-item label="最后检查">
        {{ formatCheckedAt(status?.checkedAt) }}
      </el-descriptions-item>
      <el-descriptions-item label="Ollama 版本">
        {{ status?.version || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="已安装模型">
        {{ status?.installedModelCount ?? 0 }}
      </el-descriptions-item>
      <el-descriptions-item label="正在运行模型">
        {{ status?.runningModelCount ?? 0 }}
      </el-descriptions-item>
    </el-descriptions>

    <el-alert
      v-if="runtime?.accessConfigured && !runtime.usesAccess"
      class="access-warning"
      type="warning"
      :closable="false"
      show-icon
      title="此地址不会携带服务器 Cloudflare Access 凭据"
    />

    <div v-if="isAdmin" class="status-actions">
      <el-button :loading="loading" @click="$emit('check')">检查连接</el-button>
      <el-button :loading="loading" @click="$emit('test')">普通测试</el-button>
      <el-button type="warning" :loading="loading" @click="$emit('test-generate')">生成测试</el-button>
    </div>
  </section>
</template>

<style scoped>
.ollama-status {
  margin-bottom: 18px;
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}

.status-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.status-title {
  font-weight: 600;
  line-height: 1.4;
}

.status-message {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.status-details {
  width: 100%;
}

.status-details :deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.access-warning,
.status-actions {
  margin-top: 12px;
}

.status-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.status-actions :deep(.el-button) {
  min-height: 32px;
  height: auto;
  white-space: normal;
  line-height: 1.4;
}

@media (max-width: 640px) {
  .status-header {
    align-items: stretch;
    flex-direction: column;
  }

  .status-details :deep(.el-descriptions__table),
  .status-details :deep(tbody),
  .status-details :deep(tr),
  .status-details :deep(td) {
    display: block;
    width: 100%;
  }

  .status-actions :deep(.el-button) {
    flex: 1 1 120px;
    margin-left: 0;
  }
}
</style>
